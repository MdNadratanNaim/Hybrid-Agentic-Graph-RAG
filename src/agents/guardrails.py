"""
guardrails.py - Step 1 safety gate for the Hybrid Agentic RAG pipeline.

Chains three layers, each invoked only when the previous one leaves the
verdict genuinely undecided:

    1. prompt_guard     - fast classifier, always runs, returns a float in [0, 1]
    2. safeguard_input  - LLM policy judge, runs on everything prompt_guard
                          didn't already fast-block
    3. sanitizer_agent  - LLM rewrite agent, runs whenever safeguard_input's
                          verdict is "flag" or "route_to_sanitizer" - both
                          get a chance at a clean edit rather than being
                          passed through or blocked outright. A "flag"
                          often still has an isolable bad element (e.g. an
                          encoded payload sitting next to an otherwise fine
                          question) that the sanitizer can strip even
                          though the guard wasn't confident enough to call
                          it a definite route_to_sanitizer case. The
                          sanitizer's own "nothing to remove -> pass
                          through unchanged" and "nothing salvageable ->
                          escalate_block" behavior is what keeps this safe
                          for the flags that turn out to be nothing.

Important: prompt_guard and safeguard_input both catch their own exceptions
internally and return a schema-valid "failure" value instead of raising
(prompt_guard -> {"score": None}; safeguard_input -> a full verdict dict
with categories=["Error"], recommended_action="block", confidence=1.0).
This means an exception will (almost) never actually reach this module -
a failed call looks exactly like a normal return value. So error handling
here is built around *detecting that sentinel value*, not around
try/except, and retries re-issue the call when the sentinel is seen, not
when an exception is caught. A thin try/except is still kept as a last-
resort backstop in case a future refactor of those functions removes their
internal catch-all, or in case sanitizer_agent doesn't follow the same
convention - but it is not the primary error-handling path.

Production principles applied here:

  - Fail closed. Any missing/malformed/sentinel-error data from a
    dependency blocks the request rather than letting it through silently.
  - prompt_guard is a narrow injection/jailbreak detector, not a general
    content-safety classifier. A low score only means "this doesn't look
    like an attempt to manipulate the model" - it says nothing about
    whether the content itself is otherwise harmful (e.g. a plain,
    non-adversarial request for dangerous information). Because of that,
    prompt_guard is only ever allowed to fast-track a request to a
    *stricter* outcome (block on a confident injection score), never to a
    weaker one - there is no "confidently safe, skip the judge" path.
    Every request that isn't an obvious injection still goes through
    safeguard_input's full policy check.
  - Infra failures are reported as "Error", not "Blocked". Both stop the
    request, but a real content violation and a downed dependency should
    not look identical in your logs/metrics - only one of them means
    "someone tried something bad."
  - No substring matching on action/category strings. The old version used
    `"block" in recommendation`-style checks, which can both miss schema
    drift and false-positive on unrelated text. Verdicts are matched
    against an explicit set of known values instead.
  - The 0.0-is-falsy trap. `if not score` would treat a perfectly-confident
    "safe" score of 0.0 as an error. Checked with `is None` explicitly.
  - Every branch returns the same shape, always fully populated, so
    downstream code never has to special-case a missing key.
  - Status strings are kept backward-compatible with the previous version
    ("Blocked" / "Allow" / "Sanitize" / "Error"), with "Flagged" repurposed
    rather than dropped: it no longer means "passed through unreviewed,"
    it now means "the sanitizer produced an edit but wasn't confident the
    edit preserves the original intent" - a softer outcome than a clean
    Sanitize, worth routing to human review, but still carries
    sanitized_content so the caller isn't left with nothing.
"""

import logging
from enum import Enum
from typing import Any, Optional

from agents.prompt_guard import prompt_guard
from agents.safeguard import safeguard_input
from agents.sanitizer import sanitizer_agent

logger = logging.getLogger("guardrails")

# ---------------------------------------------------------------------------
# Tunables - pull these from config/env in real deployment, not hardcoded.
# ---------------------------------------------------------------------------

# prompt_guard score band. There is deliberately only one threshold here,
# not a low/high band:
#   score > HIGH_THRESHOLD  -> confidently an injection/jailbreak attempt
#                              -> block outright, skip safeguard_input
#   score <= HIGH_THRESHOLD -> not a confident injection
#                              -> ALWAYS proceed to safeguard_input
# A low score must never skip safeguard_input. prompt_guard has no coverage
# of general content-safety categories (dangerous goods, medical harm,
# etc.) - a low score there only rules out "this is a jailbreak," not
# "this is safe." Only a confident high score is trustworthy enough to
# short-circuit anything, and only toward the stricter outcome.
PROMPT_GUARD_HIGH_THRESHOLD = 0.8

# safeguard_input / sanitizer_agent verdicts below this confidence are not
# trusted at face value. Only ever used to make an *allow-side* verdict more
# cautious - a low-confidence "block" is left as a block, since erring
# toward caution is already the safe direction.
MIN_TRUSTED_CONFIDENCE = 0.6

VALID_RISK_LEVELS = {"safe", "low_risk", "medium_risk", "high_risk"}
VALID_ACTIONS = {"allow", "flag", "route_to_sanitizer", "block"}
VALID_SANITIZER_DECISIONS = {"sanitized", "escalate_block"}

# How many times to re-issue a dependency call after seeing its error
# sentinel (or, in the backstop case, after catching a raised exception)
# before giving up and reporting Status.ERROR. Keep this low - a safety
# gate should not add several seconds of retry latency to every request.
CALL_RETRIES = 1


class Status(str, Enum):
    BLOCKED = "Blocked"
    ALLOWED = "Allow"
    SANITIZED = "Sanitize"
    FLAGGED = "Flagged"
    ERROR = "Error"


# ---------------------------------------------------------------------------
# Sentinel detection - how we recognize "the dependency call itself failed"
# ---------------------------------------------------------------------------

def _is_safeguard_error_sentinel(result: dict) -> bool:
    """True if this looks like safeguard_input's internal fail-closed dict.

    safeguard_input catches its own exceptions and returns a well-formed
    block verdict tagged with categories=["Error"] rather than raising.
    Recognizing this distinguishes "the service call failed" from "the
    model made a real safety decision" - both end up blocking, but only
    one of them is worth alerting on as an infra issue.
    """
    categories = result.get("categories") or []
    if isinstance(categories, str):
        categories = [categories]
    return any(str(c).strip().lower() == "error" for c in categories)


def _is_sanitizer_error_sentinel(result: dict) -> bool:
    """True if this looks like an equivalent fail-closed dict from sanitizer_agent.

    Assumes sanitizer_agent follows the same convention as the other two
    agents. Update this if your actual implementation signals errors
    differently (e.g. a top-level "error" key instead of a tagged
    removed_elements entry).
    """
    for item in result.get("removed_elements") or []:
        if isinstance(item, dict) and str(item.get("category", "")).strip().lower() == "error":
            return True
    return False


# ---------------------------------------------------------------------------
# Retrying wrappers - retry on the sentinel/malformed-output condition,
# with a thin try/except backstop for the (expected-to-be-rare) case where
# an exception escapes anyway.
# ---------------------------------------------------------------------------

def _get_prompt_guard_score(content: str, retries: int = CALL_RETRIES) -> Optional[float]:
    for attempt in range(retries + 1):
        try:
            raw = prompt_guard(content)
        except Exception:
            logger.exception(
                "guardrails: prompt_guard raised unexpectedly (attempt %d/%d)",
                attempt + 1,
                retries + 1,
            )
            continue

        score = raw.get("score") if isinstance(raw, dict) else None
        if score is None:
            logger.warning(
                "guardrails: prompt_guard returned no score (attempt %d/%d)",
                attempt + 1,
                retries + 1,
            )
            continue

        try:
            return float(score)
        except (TypeError, ValueError):
            logger.warning(
                "guardrails: prompt_guard returned a non-numeric score=%r (attempt %d/%d)",
                score,
                attempt + 1,
                retries + 1,
            )
            continue

    return None


def _get_safeguard_verdict(
    content: str, context: str, evaluation_type: str, retries: int = CALL_RETRIES
) -> Optional[dict]:
    last_result: Optional[dict] = None
    for attempt in range(retries + 1):
        try:
            result = safeguard_input(content, context, evaluation_type)
        except Exception:
            logger.exception(
                "guardrails: safeguard_input raised unexpectedly (attempt %d/%d)",
                attempt + 1,
                retries + 1,
            )
            continue

        if not isinstance(result, dict):
            logger.warning(
                "guardrails: safeguard_input returned a non-dict response (attempt %d/%d)",
                attempt + 1,
                retries + 1,
            )
            continue

        last_result = result
        if not _is_safeguard_error_sentinel(result):
            return result

        logger.warning(
            "guardrails: safeguard_input returned its error sentinel (attempt %d/%d)",
            attempt + 1,
            retries + 1,
        )

    # Exhausted retries - return whatever we last got (an error sentinel),
    # or None if we never got a dict back at all.
    return last_result


def _get_sanitizer_verdict(
    content: str,
    evaluation_type: str,
    guard_verdict: dict,
    context: str,
    retries: int = CALL_RETRIES,
) -> Optional[dict]:
    last_result: Optional[dict] = None
    for attempt in range(retries + 1):
        try:
            result = sanitizer_agent(content, evaluation_type, guard_verdict, context)
        except Exception:
            logger.exception(
                "guardrails: sanitizer_agent raised unexpectedly (attempt %d/%d)",
                attempt + 1,
                retries + 1,
            )
            continue

        if not isinstance(result, dict):
            logger.warning(
                "guardrails: sanitizer_agent returned a non-dict response (attempt %d/%d)",
                attempt + 1,
                retries + 1,
            )
            continue

        last_result = result
        if not _is_sanitizer_error_sentinel(result):
            return result

        logger.warning(
            "guardrails: sanitizer_agent returned its error sentinel (attempt %d/%d)",
            attempt + 1,
            retries + 1,
        )

    return last_result


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------

def _safe_categories(raw: Any) -> str:
    """Join a categories list defensively; never raise on odd input shapes."""
    if not raw:
        return "Uncategorized"
    if isinstance(raw, str):
        return raw
    try:
        return ". ".join(str(c) for c in raw)
    except TypeError:
        return "Uncategorized"


def _safe_float(raw: Any, default: float = 0.0) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _response(
    status: Status,
    category: str,
    reason: str,
    sanitized_content: Optional[str] = None,
    *,
    risk_level: Optional[str] = None,
    confidence: Optional[float] = None,
    stage: Optional[str] = None,
    prompt_guard_score: Optional[float] = None,
    intent_preserved: Optional[bool] = None,
    guard_action: Optional[str] = None,
) -> dict:
    """Single place that shapes every return value, so the schema never drifts."""
    return {
        "status": status.value,
        "category": category,
        "reason": reason,
        "sanitized_content": sanitized_content,
        "risk_level": risk_level,
        "confidence": confidence,
        "stage": stage,
        "prompt_guard_score": prompt_guard_score,
        "intent_preserved": intent_preserved,
        "guard_action": guard_action,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def guardrails(content: str, context: str = "", evaluation_type: str = "user_prompt") -> dict:
    """
    Step-1 safety gate: prompt_guard -> safeguard_input -> sanitizer_agent.

    Returns:
        {
            "status": "Blocked" | "Allow" | "Sanitize" | "Flagged" | "Error",
            "category": str,
            "reason": str,
            "sanitized_content": str | None,
            "risk_level": str | None,
            "confidence": float | None,
            "stage": str | None,               # which layer produced the final verdict
            "prompt_guard_score": float | None, # raw fast-classifier score, for audit
            "intent_preserved": bool | None,    # only set on Sanitize/Flagged outcomes
            "guard_action": str | None,         # safeguard_input's original verdict
                                                 # ("allow"/"flag"/"route_to_sanitizer"/
                                                 # "block"), before any guardrails.py-
                                                 # level downgrade - lets you see e.g.
                                                 # how often a "flag" ends up sanitized.
        }
    """

    # ---- Input validation --------------------------------------------------
    if not isinstance(content, str) or not content.strip():
        return _response(
            Status.ERROR,
            "Error",
            "Empty or invalid content passed to guardrails.",
            stage="input_validation",
        )

    if evaluation_type not in {"user_prompt", "retrieved_content", "tool_output"}:
        logger.warning("guardrails: unexpected evaluation_type=%r", evaluation_type)

    # ---- Layer 1: prompt_guard (fast classifier, always runs) -------------
    pg_score = _get_prompt_guard_score(content)

    if pg_score is None:
        return _response(
            Status.ERROR,
            "Error",
            "Prompt guard service failed to return a usable score.",
            stage="prompt_guard",
        )

    if not 0.0 <= pg_score <= 1.0:
        logger.warning("guardrails: prompt_guard score out of range: %s", pg_score)
        pg_score = min(max(pg_score, 0.0), 1.0)

    # Confidently an injection/jailbreak attempt -> block without waiting on
    # the LLM judge. This is the only fast-path allowed: it only ever makes
    # the gate stricter, never weaker.
    if pg_score > PROMPT_GUARD_HIGH_THRESHOLD:
        return _response(
            Status.BLOCKED,
            "Prompt Injection / Jailbreak",
            f"Prompt guard confidently flagged this input (score={pg_score:.2f}).",
            risk_level="high_risk",
            stage="prompt_guard",
            prompt_guard_score=pg_score,
        )

    # Everything else - including a very low score - proceeds to the full
    # content-safety judge. Clearing prompt_guard only means "not a
    # detected injection/jailbreak attempt," not "safe content." There is
    # no skip-to-allow path here.

    # ---- Layer 2: safeguard_input (LLM judge - runs on every request that
    # wasn't already fast-blocked above) -------------------------------
    result = _get_safeguard_verdict(content, context, evaluation_type)

    if result is None:
        return _response(
            Status.ERROR,
            "Error",
            "Safeguard input service returned no usable response.",
            stage="safeguard_input",
            prompt_guard_score=pg_score,
        )

    if _is_safeguard_error_sentinel(result):
        return _response(
            Status.ERROR,
            "Error",
            str(result.get("reason") or "Safeguard input service failed."),
            risk_level=str(result.get("risk_level") or "").lower() or None,
            confidence=_safe_float(result.get("confidence"), default=1.0),
            stage="safeguard_input",
            prompt_guard_score=pg_score,
        )

    risk_level = str(result.get("risk_level") or "").lower()
    recommendation = str(result.get("recommended_action") or "").lower()
    reason = result.get("reason") or "No reason provided."
    category = _safe_categories(result.get("categories"))
    confidence = _safe_float(result.get("confidence"))

    if risk_level not in VALID_RISK_LEVELS or recommendation not in VALID_ACTIONS:
        logger.error(
            "guardrails: safeguard_input returned unrecognized schema: risk_level=%r action=%r",
            risk_level,
            recommendation,
        )
        return _response(
            Status.BLOCKED,
            "Error",
            "Safeguard input returned an unrecognized verdict; failing closed.",
            risk_level=risk_level or None,
            confidence=confidence,
            stage="safeguard_input",
            prompt_guard_score=pg_score,
        )

    original_recommendation = recommendation  # kept for guard_action, pre-downgrade

    # Contradiction guard: HIGH_RISK paired with "allow" is either a model
    # mistake or a sign the judge was manipulated. Don't trust it at face
    # value - downgrade instead of blindly allowing.
    if risk_level == "high_risk" and recommendation == "allow":
        logger.warning(
            "guardrails: safeguard_input returned allow with high_risk - downgrading to flag"
        )
        recommendation = "flag"

    # Low-confidence "allow" is downgraded to "flag" rather than trusted at
    # face value. "flag" and "route_to_sanitizer" are deliberately NOT
    # downgraded further here: both now go to the sanitizer regardless of
    # confidence, and the sanitizer's own escalate_block is the safety net
    # for cases that turn out to have nothing salvageable. Blocking a
    # low-confidence route_to_sanitizer outright (the old behavior) would
    # have denied requests the guard itself wasn't sure needed denying.
    if confidence < MIN_TRUSTED_CONFIDENCE and recommendation == "allow":
        logger.info("guardrails: low-confidence allow (%.2f) downgraded to flag", confidence)
        recommendation = "flag"

    if recommendation == "block":
        return _response(
            Status.BLOCKED,
            category,
            reason,
            risk_level=risk_level,
            confidence=confidence,
            stage="safeguard_input",
            prompt_guard_score=pg_score,
            guard_action=original_recommendation,
        )

    if recommendation == "allow":
        return _response(
            Status.ALLOWED,
            category,
            reason,
            risk_level=risk_level,
            confidence=confidence,
            stage="safeguard_input",
            prompt_guard_score=pg_score,
            guard_action=original_recommendation,
        )

    # recommendation is "flag" or "route_to_sanitizer" from here on - both
    # go to the sanitizer. See module docstring for why "flag" isn't just
    # passed through anymore.
    # ---- Layer 3: sanitizer_agent ------------------------------------
    sanitizer_result = _get_sanitizer_verdict(content, evaluation_type, result, context)

    if sanitizer_result is None:
        return _response(
            Status.ERROR,
            "Error",
            "Sanitizer service returned no usable response.",
            risk_level=risk_level,
            confidence=confidence,
            stage="sanitizer_agent",
            prompt_guard_score=pg_score,
            guard_action=original_recommendation,
        )

    if _is_sanitizer_error_sentinel(sanitizer_result):
        return _response(
            Status.ERROR,
            "Error",
            "Sanitizer service failed while attempting to sanitize flagged content.",
            risk_level=risk_level,
            confidence=confidence,
            stage="sanitizer_agent",
            prompt_guard_score=pg_score,
            guard_action=original_recommendation,
        )

    sanitizer_decision = str(sanitizer_result.get("decision") or "").lower()
    sanitized_content = sanitizer_result.get("sanitized_content")
    intent_preserved = sanitizer_result.get("intent_preserved", True)
    sanitizer_confidence = _safe_float(sanitizer_result.get("confidence"))

    if sanitizer_decision not in VALID_SANITIZER_DECISIONS:
        logger.error(
            "guardrails: sanitizer_agent returned unrecognized decision=%r", sanitizer_decision
        )
        return _response(
            Status.BLOCKED,
            category,
            "Sanitizer returned an unrecognized verdict; failing closed.",
            risk_level=risk_level,
            confidence=confidence,
            stage="sanitizer_agent",
            prompt_guard_score=pg_score,
            guard_action=original_recommendation,
        )

    # escalate_block, or a "sanitized" decision that somehow carries no
    # content - both fail closed rather than letting empty/partial content
    # silently pass through. This is also where an over-flagged, nothing-
    # wrong-here case would land if the sanitizer got that wrong - but per
    # its own prompt, "nothing to remove" is supposed to come back as
    # decision=sanitized with content unchanged, not escalate_block, so
    # this branch should only fire on genuine no-legitimate-core content.
    if sanitizer_decision == "escalate_block" or not sanitized_content:
        return _response(
            Status.BLOCKED,
            category,
            "Content could not be safely sanitized: " + reason,
            risk_level=risk_level,
            confidence=confidence,
            stage="sanitizer_agent",
            prompt_guard_score=pg_score,
            guard_action=original_recommendation,
        )

    if not intent_preserved:
        # Sanitizer produced output but isn't confident it still represents
        # the original ask. Returned as Flagged rather than Sanitize - the
        # caller still gets sanitized_content to use if it wants, but the
        # status makes clear this is a lower-confidence result worth
        # routing to human review rather than treating as a clean win.
        logger.warning(
            "guardrails: sanitizer_agent produced output but intent_preserved=False"
        )
        return _response(
            Status.FLAGGED,
            category,
            reason,
            sanitized_content,
            risk_level=risk_level,
            confidence=sanitizer_confidence,
            stage="sanitizer_agent",
            prompt_guard_score=pg_score,
            intent_preserved=False,
            guard_action=original_recommendation,
        )

    return _response(
        Status.SANITIZED,
        category,
        reason,
        sanitized_content,
        risk_level=risk_level,
        confidence=sanitizer_confidence,
        stage="sanitizer_agent",
        prompt_guard_score=pg_score,
        intent_preserved=True,
        guard_action=original_recommendation,
    )
