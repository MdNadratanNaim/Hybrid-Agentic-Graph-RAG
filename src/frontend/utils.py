"""
utils.py
--------
Session-state management, shared pipeline metadata, local (disk-backed)
persistence for conversation history / saved runs, and small formatting
helpers used across the frontend.

Nothing in this file talks to the agent pipeline directly — it is pure
frontend plumbing. `workflow_runner.py` and `components.py` both import
STAGE_META from here so the IDs used to report progress and the IDs used
to render the signal-path rail can never drift apart.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).resolve().parent
ASSETS_DIR = FRONTEND_DIR / "assets"
DATA_DIR = FRONTEND_DIR / ".data"
HISTORY_FILE = DATA_DIR / "conversation_history.json"
SAVED_RUNS_FILE = DATA_DIR / "saved_runs.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Pipeline stage metadata — the single source of truth for stage IDs.
# Numbers match the architecture doc 1:1 so the on-screen rail is directly
# traceable back to the design. workflow_runner.py yields these IDs;
# components.py renders them.
# --------------------------------------------------------------------------

STAGE_META: "OrderedDict[str, dict]" = OrderedDict(
    [
        ("input_guard", {"num": 1, "code": "SAFE·IN", "label": "Input Safety",
                          "desc": "guardrails(): prompt_guard → safeguard_input → sanitizer_agent."}),
        ("planner", {"num": 2, "code": "PLAN", "label": "Planner / Router",
                     "desc": "Classifies query complexity and decides which stages run."}),
        ("rewriter", {"num": 3, "code": "REWRITE", "label": "Query Rewriter",
                      "desc": "Decomposes into sub-questions, tags each with a retrieval tool."}),
        ("retrieval", {"num": 4, "code": "RETRIEVE", "label": "Retrieval",
                       "desc": "Hybrid dense + BM25 search, plus web / SQL / API as tagged."}),
        ("rerank", {"num": 5, "code": "RERANK", "label": "Reranker",
                    "desc": "Cross-encoder re-scores candidates, cuts to top-n."}),
        ("summarizer", {"num": 6, "code": "SUMM", "label": "Summarizer",
                        "desc": "Condenses each chunk to essential facts, in parallel."}),
        ("graph", {"num": 7, "code": "GRAPH", "label": "Graph Extractor",
                  "desc": "Entities / relationships / claims → subgraph. Multi-hop & comparison only."}),
        ("reasoner", {"num": 8, "code": "REASON", "label": "Reasoner",
                     "desc": "Resolves contradictions, produces a structured reasoning trace."}),
        ("sufficiency", {"num": 9, "code": "CHECK", "label": "Sufficiency Check",
                         "desc": "Sufficient → proceed. Otherwise reformulate or re-retrieve."}),
        ("generator", {"num": 10, "code": "GEN", "label": "Answer Generator",
                       "desc": "Synthesizes the final answer with explicit citations."}),
        ("critic", {"num": 11, "code": "CRITIC", "label": "Critic",
                   "desc": "Hallucination check, factual consistency, completeness."}),
        ("corrective", {"num": 12, "code": "LOOP", "label": "Corrective Loop",
                        "desc": "Shares the 3-iteration cap with the sufficiency check."}),
        ("output_guard", {"num": 13, "code": "SAFE·OUT", "label": "Output Safety",
                          "desc": "Final policy / harmful-content check before returning."}),
    ]
)

STAGE_ORDER = list(STAGE_META.keys())

# --------------------------------------------------------------------------
# Retrieval-source override, offered in the query composer's advanced
# options. Sources reflect what's actually in the architecture: the
# rewriter tags each sub-question with a tool ("vector" | "web" | "sql" |
# "api"), and "Auto" just leaves that choice to the rewriter/router. There
# is no separate "hybrid" *source* — dense+BM25 hybrid search is always-on
# inside the vector tool itself, not a user-facing toggle — so it isn't
# listed here to avoid implying it's a distinct option.
# --------------------------------------------------------------------------

RETRIEVAL_SOURCE_OPTIONS = [
    "Auto — router decides per sub-question",
    "Vector DB only",
    "Web search only",
    "SQL only",
    "API only",
    "No retrieval — answer from model's own knowledge",
]

RETRIEVAL_SOURCE_MAP = {
    "Auto — router decides per sub-question": None,
    "Vector DB only": "vector",
    "Web search only": "web",
    "SQL only": "sql",
    "API only": "api",
    "No retrieval — answer from model's own knowledge": "none",
}

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"


# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------

def init_session_state() -> None:
    defaults = {
        # [{"role": "user", "content": str, "ts": float} |
        #  {"role": "assistant", "content": str, "ts": float, "run": dict}]
        "chat_history": [],
        "current_run": None,         # last completed run result (dict) or None
        "viewing_saved_run": None,   # a saved run opened from the sidebar, shown above the chat
        "stage_status": {sid: STATUS_PENDING for sid in STAGE_ORDER},
        "run_logs": [],              # [{"stage": str, "detail": str, "ms": float}]
        "theme": "dark",
        "saved_runs": load_saved_runs(),
        "is_running": False,
        "session_id": str(uuid.uuid4())[:8],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_stage_status() -> None:
    st.session_state.stage_status = {sid: STATUS_PENDING for sid in STAGE_ORDER}
    st.session_state.run_logs = []


def new_session() -> None:
    st.session_state.chat_history = []
    st.session_state.current_run = None
    st.session_state.viewing_saved_run = None
    st.session_state.session_id = str(uuid.uuid4())[:8]
    reset_stage_status()


# --------------------------------------------------------------------------
# Disk persistence (simple JSON files — swap for a DB later if needed)
# --------------------------------------------------------------------------

def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, data: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        st.warning(f"Could not persist to {path.name}: {e}")


def load_saved_runs() -> list[dict]:
    return _load_json(SAVED_RUNS_FILE, [])


def persist_saved_runs(runs: list[dict]) -> None:
    _save_json(SAVED_RUNS_FILE, runs)


def save_run(run_result: dict) -> None:
    """Persist a completed run so it survives a browser refresh / restart.
    Idempotent by run_id: saving the same run twice (a double click, or
    re-saving a run reopened from the sidebar) updates it in place instead
    of adding a duplicate sidebar entry."""
    run_id = run_result.get("run_id")
    runs = [r for r in load_saved_runs() if r.get("run_id") != run_id]
    runs.insert(0, run_result)
    runs = runs[:100]  # keep the most recent 100
    persist_saved_runs(runs)
    st.session_state.saved_runs = runs


def delete_saved_run(run_id: str) -> None:
    runs = [r for r in load_saved_runs() if r.get("run_id") != run_id]
    persist_saved_runs(runs)
    st.session_state.saved_runs = runs


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------

def format_ms(ms: float | None) -> str:
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms / 1000:.2f} s"


def truncate(text: str, n: int = 220) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_run_id() -> str:
    return f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"


def safe_get(d: dict | None, key: str, default: Any = None) -> Any:
    """Defensive dict access — agent functions are external code; don't let
    a missing key crash the UI."""
    if not isinstance(d, dict):
        return default
    return d.get(key, default)


# --------------------------------------------------------------------------
# Report export
# --------------------------------------------------------------------------

def build_report_markdown(run: dict) -> str:
    lines = [
        f"# Research Assistant — Run Report",
        "",
        f"**Query:** {safe_get(run, 'query', '')}",
        f"**Generated:** {safe_get(run, 'timestamp', now_iso())}",
        f"**Confidence:** {safe_get(run, 'confidence', 0):.0%}"
        if isinstance(safe_get(run, "confidence", 0), (int, float)) else "",
        f"**Iterations used:** {safe_get(run, 'iterations_used', 0)} / {safe_get(run, 'max_iterations', 3)}",
        "",
        "## Answer",
        "",
        safe_get(run, "answer", "_No answer generated._"),
        "",
        "## Sources",
        "",
    ]
    for src in safe_get(run, "sources", []) or []:
        label = safe_get(src, "source", "Unknown source")
        score = safe_get(src, "score", None)
        score_txt = f" (score: {score:.2f})" if isinstance(score, (int, float)) else ""
        lines.append(f"- {label}{score_txt}")

    reasoning = safe_get(run, "reasoning_trace", None)
    if reasoning:
        lines += ["", "## Reasoning Trace", "", str(reasoning)]

    logs = safe_get(run, "logs", []) or []
    if logs:
        lines += ["", "## Execution Log", ""]
        for entry in logs:
            stage = safe_get(entry, "stage", "?")
            detail = safe_get(entry, "detail", "")
            ms = safe_get(entry, "ms", None)
            lines.append(f"- `{stage}` — {detail} ({format_ms(ms)})")

    return "\n".join(l for l in lines if l is not None)