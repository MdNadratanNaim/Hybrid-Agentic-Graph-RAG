"""
workflow_runner.py
-------------------
Orchestrates one query through the hybrid agentic + graph RAG pipeline by
calling the stage functions in `agents.all` directly (no separate
`workflow.py` orchestrator — this module *is* the orchestrator, so the
Streamlit frontend can report live, per-stage progress).

`run_pipeline()` is a GENERATOR. It yields a small event dict after every
stage transition so `app.py` can update the signal-path UI live, in the
same Streamlit script run (no polling / threading required):

    {"type": "stage", "stage": <id from utils.STAGE_META>,
     "status": "running" | "done" | "skipped" | "failed",
     "detail": str, "ms": float | None}

    {"type": "final", "result": <result dict, see bottom of file>}

    {"type": "error", "message": str}   # unrecoverable failure

--------------------------------------------------------------------------
CONTRACT — every function imported from `agents.all`, with the return
shape this frontend expects. If the real implementation in
`src/agents/all.py` returns something different, the frontend will still
run (all reads are defensive, via utils.safe_get) but fields may show as
blank, so please keep these shapes.
--------------------------------------------------------------------------

ingest_documents(files: list, options: dict) -> dict
    {
        "ingested": int,
        "doc_ids": list[str],
        "errors": list[str],
    }

rewrite_query(query: str, chat_history: list[dict], query_type: str) -> dict
    {
        "sub_questions": [
            {"question": str, "tool": "vector" | "web" | "sql" | "api"}, ...
        ],
    }

retrieve(sub_questions: list[dict], options: dict) -> dict
    {
        "candidates": [
            {"id": str, "text": str, "source": str, "score": float,
             "tool": str, "metadata": dict}, ...
        ],
    }

rerank(query: str, candidates: list[dict], top_n: int) -> dict
    {
        "reranked": [
            {"id": str, "text": str, "source": str, "score": float,
             "metadata": dict}, ...
        ],
    }

summarize_chunks(chunks: list[dict]) -> dict
    {
        "summaries": [
            {"id": str, "summary": str, "source": str}, ...
        ],
    }

extract_graph(summaries: list[dict]) -> dict
    {
        "nodes": [{"id": str, "label": str, "type": str}, ...],
        "edges": [{"source": str, "target": str, "relation": str}, ...],
    }

reason_over_evidence(query: str, summaries: list[dict], graph: dict | None) -> dict
    {
        "reasoning_trace": str,
        "contradictions": list[str],
        "key_facts": list[str],
    }

check_sufficiency(query: str, reasoning_trace: dict) -> dict
    {
        "sufficient": bool,
        "action": "proceed" | "reformulate" | "re_retrieve",
        "missing_info": str | None,
    }

generate_answer(query: str, reasoning_trace: dict | None, summaries: list[dict]) -> dict
    {
        "answer": str,
        "citations": [{"claim": str, "source": str}, ...],
        "uncited_claims": list[str],
        "confidence": float,            # 0-1
    }

critic_check(answer: dict, summaries: list[dict]) -> dict
    {
        "passes": bool,
        "issues": list[str],
        "hallucination_risk": "low" | "medium" | "high",
    }

output_guard(answer_text: str) -> dict
    {
        "safe": bool,
        "filtered_text": str | None,
        "reason": str | None,
    }
--------------------------------------------------------------------------
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Generator

# `frontend/` and `src/` are expected to be sibling directories under the
# project root. Adjust here if your layout differs.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


from agents.guardrails import guardrails
from agents.planner import classify_query
from agents.all import (
    ingest_documents,
    rewrite_query,
    retrieve,
    rerank,
    summarize_chunks,
    extract_graph,
    reason_over_evidence,
    check_sufficiency,
    generate_answer,
    critic_check,
    output_guard,
)

from utils import RETRIEVAL_SOURCE_MAP, safe_get, new_run_id, now_iso

HARD_ITERATION_CAP = 3


def _call(fn, *args, **kwargs) -> tuple[dict | None, float, str | None]:
    """Time a stage call and catch errors so one flaky stage can't crash
    the whole run. Returns (result, elapsed_ms, error_message)."""
    start = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
        ms = (time.perf_counter() - start) * 1000
        return result, ms, None
    except Exception as e:  # noqa: BLE001 — deliberately broad: any stage may fail
        ms = (time.perf_counter() - start) * 1000
        return None, ms, str(e)


def resolve_routing(query_type: str, needs_retrieval: bool) -> dict:
    """Implements the complexity routing table from the architecture doc."""
    if query_type == "direct_answer" or not needs_retrieval:
        return dict(rewriter=False, retrieval=False, rerank=False,
                    summarizer=False, graph=False, reasoner=False,
                    sufficiency=False, corrective_loop=False)
    if query_type == "single_hop":
        return dict(rewriter=True, retrieval=True, rerank=True,
                    summarizer=True, graph=False, reasoner=True,
                    sufficiency=True, corrective_loop=True)
    if query_type in ("multi_hop", "comparison"):
        return dict(rewriter=True, retrieval=True, rerank=True,
                    summarizer=True, graph=True, reasoner=True,
                    sufficiency=True, corrective_loop=True)
    if query_type == "calculation":
        return dict(rewriter=True, retrieval=needs_retrieval, rerank=needs_retrieval,
                    summarizer=False, graph=False, reasoner=True,
                    sufficiency=True, corrective_loop=True)
    # Unknown label from the planner — fail safe to the full pipeline.
    return dict(rewriter=True, retrieval=True, rerank=True,
                summarizer=True, graph=True, reasoner=True,
                sufficiency=True, corrective_loop=True)


def run_pipeline(
    query: str,
    files: list,
    options: dict,
    chat_history: list[dict],
) -> Generator[dict, None, None]:
    """Runs the full pipeline for one query, yielding progress events."""

    logs: list[dict] = []
    run_id = new_run_id()
    max_iterations = min(int(options.get("max_corrective_loops", HARD_ITERATION_CAP)), HARD_ITERATION_CAP)

    def log(stage: str, status: str, detail: str = "", ms: float | None = None) -> dict:
        entry = {"stage": stage, "status": status, "detail": detail, "ms": ms}
        logs.append(entry)
        return {"type": "stage", **entry}

    # ---------------------------------------------------------------- 1/13
    # One call covers the full cascade: prompt_guard -> safeguard_input ->
    # sanitizer_agent.
    yield log("input_guard", "running", "Running prompt_guard → safeguard_input → sanitizer_agent…")
    guard, ms, err = _call(guardrails, query)
    if err:
        yield log("input_guard", "failed", err, ms)
        yield {"type": "error", "message": f"Guardrails check failed: {err}"}
        return

    status = safe_get(guard, "status", "Allow")
    category = safe_get(guard, "category", "")
    reason = safe_get(guard, "reason", "")
    stage_used = safe_get(guard, "stage")
    guard_action = safe_get(guard, "guard_action")
    pg_score = safe_get(guard, "prompt_guard_score")

    detail_parts = [f"status={status}"]
    if stage_used:
        detail_parts.append(f"final_stage={stage_used}")
    if guard_action:
        detail_parts.append(f"safeguard_verdict={guard_action}")
    if isinstance(pg_score, (int, float)):
        detail_parts.append(f"prompt_guard_score={pg_score:.2f}")
    yield log("input_guard", "failed" if status == "Error" else "done", ", ".join(detail_parts), ms)

    if status == "Error":
        yield {"type": "error", "message": f"Guardrails returned an error: {reason or category}"}
        return

    if status == "Blocked":
        yield {"type": "final", "result": _blocked_result(run_id, query, reason or category)}
        return

    working_query = query
    flagged_for_review = False
    if status in ("Sanitize", "Flagged"):
        sanitized_content = safe_get(guard, "sanitized_content")
        working_query = sanitized_content or query
        flagged_for_review = status == "Flagged" or safe_get(guard, "intent_preserved", True) is False

    # ---------------------------------------------------------------- 2/13
    yield log("planner", "running", "Classifying query complexity…")
    plan, ms, err = _call(classify_query, working_query, chat_history)
    if err:
        yield log("planner", "failed", err, ms)
        yield {"type": "error", "message": f"Planner failed: {err}"}
        return
    query_type = safe_get(plan, "query_type", "single_hop")
    needs_retrieval = safe_get(plan, "needs_retrieval", True)

    # Manual retrieval-source override from the query composer, if the user
    # picked something other than "Auto".
    forced_source = RETRIEVAL_SOURCE_MAP.get(options.get("retrieval_source"))
    override_note = ""
    if forced_source == "none" and needs_retrieval:
        override_note = " (overridden: user forced no-retrieval)"
        needs_retrieval = False
        query_type = "direct_answer"
    elif forced_source in ("vector", "web", "sql", "api"):
        if not needs_retrieval:
            override_note = f" (overridden: user forced {forced_source}-only retrieval)"
            needs_retrieval = True
            if query_type == "direct_answer":
                query_type = "single_hop"
        else:
            override_note = f" (source forced to {forced_source}-only)"

    yield log("planner", "done", f"type={query_type}, retrieval={needs_retrieval}{override_note}", ms)

    routing = resolve_routing(query_type, needs_retrieval)

    # Optional document ingestion happens once, regardless of loop iterations.
    if files:
        yield log("retrieval", "running", f"Ingesting {len(files)} uploaded document(s)…")
        ingested, ms, err = _call(ingest_documents, files, options)
        if err:
            yield log("retrieval", "failed", f"Ingestion error: {err}", ms)
        else:
            yield log("retrieval", "done", f"Ingested {safe_get(ingested, 'ingested', 0)} document(s).", ms)

    for skipped_stage, enabled in [
        ("rewriter", routing["rewriter"]), ("retrieval", routing["retrieval"]),
        ("rerank", routing["rerank"]), ("summarizer", routing["summarizer"]),
        ("graph", routing["graph"]), ("reasoner", routing["reasoner"]),
        ("sufficiency", routing["sufficiency"]),
    ]:
        if skipped_stage == "retrieval" and files:
            continue  # already reported via document ingestion above
        if not enabled:
            yield log(skipped_stage, "skipped", "Not needed for this query type.")

    summaries: list[dict] = []
    graph: dict | None = None
    reasoning_trace: dict | None = None
    iterations_used = 0
    capped_out = False

    # -------------------------------------------------------- 3-9 (looped)
    if routing["retrieval"] or routing["rewriter"]:
        loop_query = working_query
        while True:
            summaries, graph, reasoning_trace, sub_ms = yield from _retrieve_reason_cycle(
                loop_query, working_query, chat_history, query_type, routing, options, log, forced_source
            )

            if not routing["sufficiency"] or reasoning_trace is None:
                break

            yield log("sufficiency", "running", "Checking whether evidence is sufficient…")
            suff, ms, err = _call(check_sufficiency, working_query, reasoning_trace)
            if err:
                yield log("sufficiency", "failed", err, ms)
                break
            sufficient = safe_get(suff, "sufficient", True)
            action = safe_get(suff, "action", "proceed")
            yield log("sufficiency", "done", f"sufficient={sufficient}, action={action}", ms)

            if sufficient or iterations_used >= max_iterations:
                capped_out = capped_out or (not sufficient and iterations_used >= max_iterations)
                break

            iterations_used += 1
            missing = safe_get(suff, "missing_info", "")
            loop_query = f"{working_query} (additional context needed: {missing})" if missing else working_query
            yield log("planner", "running", f"Re-planning (iteration {iterations_used}/{max_iterations}, action={action})…")
            yield log("planner", "done", "Looping back to query rewriter / retrieval.")
    # else: retrieval/rewriter both off (direct_answer) — already logged as
    # skipped by the routing loop above, straight through to the generator.

    # -------------------------------------------------------------- 10-12
    while True:
        yield log("generator", "running", "Synthesizing answer…")
        answer, ms, err = _call(generate_answer, working_query, reasoning_trace, summaries)
        if err:
            yield log("generator", "failed", err, ms)
            yield {"type": "error", "message": f"Answer generation failed: {err}"}
            return
        uncited = safe_get(answer, "uncited_claims", [])
        detail = f"{len(safe_get(answer, 'citations', []))} citation(s)"
        if uncited:
            detail += f", {len(uncited)} uncited claim(s) flagged"
        yield log("generator", "done", detail, ms)

        yield log("critic", "running", "Checking for hallucination / consistency…")
        critic, ms, err = _call(critic_check, answer, summaries)
        if err:
            yield log("critic", "failed", err, ms)
            break
        passes = safe_get(critic, "passes", True)
        risk = safe_get(critic, "hallucination_risk", "low")
        yield log("critic", "done", f"passes={passes}, hallucination_risk={risk}", ms)

        if passes or not routing["corrective_loop"] or iterations_used >= max_iterations:
            capped_out = capped_out or (not passes and iterations_used >= max_iterations)
            break

        iterations_used += 1
        yield log("corrective", "running",
                   f"Critic flagged issues — re-retrieving (iteration {iterations_used}/{max_iterations})…")
        summaries, graph, reasoning_trace, _ = yield from _retrieve_reason_cycle(
            working_query, working_query, chat_history, query_type, routing, options, log, forced_source
        )
        yield log("corrective", "done", "Re-generation in progress.")

    # ---------------------------------------------------------------- 13
    yield log("output_guard", "running", "Final policy / safety check…")
    out_guard, ms, err = _call(output_guard, safe_get(answer, "answer", ""))
    final_answer_text = safe_get(answer, "answer", "")
    if err:
        yield log("output_guard", "failed", err, ms)
    else:
        if not safe_get(out_guard, "safe", True):
            final_answer_text = safe_get(out_guard, "filtered_text") or (
                "The generated answer was withheld by the output safety gate."
            )
            yield log("output_guard", "done", f"blocked: {safe_get(out_guard, 'reason', '')}", ms)
        else:
            yield log("output_guard", "done", "passed", ms)

    result = {
        "run_id": run_id,
        "query": query,
        "sanitized_query": working_query if working_query != query else None,
        "flagged_for_review": flagged_for_review,
        "guard_status": status,
        "guard_category": category or None,
        "query_type": query_type,
        "answer": final_answer_text,
        "confidence": safe_get(answer, "confidence", 0.0),
        "citations": safe_get(answer, "citations", []),
        "uncited_claims": safe_get(answer, "uncited_claims", []),
        "sources": summaries or [],
        "reasoning_trace": safe_get(reasoning_trace, "reasoning_trace", None) if reasoning_trace else None,
        "key_facts": safe_get(reasoning_trace, "key_facts", []) if reasoning_trace else [],
        "graph": graph,
        "critic_issues": safe_get(critic, "issues", []),
        "iterations_used": iterations_used,
        "max_iterations": max_iterations,
        "capped_out": capped_out,
        "logs": logs,
        "timestamp": now_iso(),
    }
    yield {"type": "final", "result": result}


def _retrieve_reason_cycle(
    loop_query: str,
    original_query: str,
    chat_history: list[dict],
    query_type: str,
    routing: dict,
    options: dict,
    log,
    forced_source: str | None = None,
):
    """Shared sub-pipeline for stages 3-8 (rewriter through reasoner). A
    plain function can't `yield`, so this is a generator that `run_pipeline`
    drives with `yield from`, and it returns (summaries, graph, reasoning,
    elapsed_ms) as its StopIteration value.

    `forced_source` (one of "vector" | "web" | "sql" | "api" | None) comes
    from the query composer's retrieval-source override — when set, every
    sub-question's tool tag is pinned to it instead of whatever the
    rewriter would otherwise pick."""

    candidates: list[dict] = []
    reranked: list[dict] = []
    summaries: list[dict] = []
    graph: dict | None = None
    reasoning_trace: dict | None = None
    default_tool = forced_source if forced_source in ("vector", "web", "sql", "api") else "vector"

    if routing["rewriter"]:
        yield log("rewriter", "running", "Decomposing into sub-questions…")
        rewritten, ms, err = _call(rewrite_query, loop_query, chat_history, query_type)
        sub_questions = safe_get(rewritten, "sub_questions", [{"question": loop_query, "tool": default_tool}]) if not err else [{"question": loop_query, "tool": default_tool}]
        if forced_source in ("vector", "web", "sql", "api"):
            for sq in sub_questions:
                sq["tool"] = forced_source
        yield log("rewriter", "failed" if err else "done", err or f"{len(sub_questions)} sub-question(s)", ms)
    else:
        sub_questions = [{"question": loop_query, "tool": default_tool}]

    if routing["retrieval"]:
        yield log("retrieval", "running", f"Retrieving for {len(sub_questions)} sub-question(s)…")
        retrieved, ms, err = _call(retrieve, sub_questions, options)
        candidates = safe_get(retrieved, "candidates", []) if not err else []
        yield log("retrieval", "failed" if err else "done", err or f"{len(candidates)} candidate(s)", ms)

    if routing["rerank"] and candidates:
        yield log("rerank", "running", f"Reranking {len(candidates)} candidate(s)…")
        top_n = int(options.get("top_k", 5))
        reranked_resp, ms, err = _call(rerank, original_query, candidates, top_n)
        reranked = safe_get(reranked_resp, "reranked", candidates[:top_n]) if not err else candidates[:top_n]
        yield log("rerank", "failed" if err else "done", err or f"kept top {len(reranked)}", ms)
    else:
        reranked = candidates

    if routing["summarizer"] and reranked:
        yield log("summarizer", "running", f"Summarizing {len(reranked)} chunk(s) (batched)…")
        summarized, ms, err = _call(summarize_chunks, reranked)
        summaries = safe_get(summarized, "summaries", []) if not err else []
        yield log("summarizer", "failed" if err else "done", err or f"{len(summaries)} summary(ies)", ms)
    else:
        summaries = reranked

    if routing["graph"] and summaries:
        yield log("graph", "running", "Extracting entities / relationships…")
        graph_resp, ms, err = _call(extract_graph, summaries)
        graph = graph_resp if not err else None
        n_nodes = len(safe_get(graph, "nodes", [])) if graph else 0
        n_edges = len(safe_get(graph, "edges", [])) if graph else 0
        yield log("graph", "failed" if err else "done", err or f"{n_nodes} node(s), {n_edges} edge(s)", ms)

    if routing["reasoner"]:
        yield log("reasoner", "running", "Reasoning over evidence…")
        reasoning_trace, ms, err = _call(reason_over_evidence, original_query, summaries, graph)
        yield log("reasoner", "failed" if err else "done", err or "reasoning trace produced", ms)

    return summaries, graph, reasoning_trace, None


def _blocked_result(run_id: str, query: str, reason: str) -> dict:
    return {
        "run_id": run_id,
        "query": query,
        "sanitized_query": None,
        "query_type": None,
        "answer": (
            "This request couldn't be processed: it was flagged by the input "
            f"safety gate and could not be safely rewritten ({reason})."
        ),
        "confidence": 0.0,
        "citations": [],
        "uncited_claims": [],
        "sources": [],
        "reasoning_trace": None,
        "key_facts": [],
        "graph": None,
        "critic_issues": [],
        "iterations_used": 0,
        "max_iterations": 0,
        "capped_out": False,
        "blocked": True,
        "logs": [],
        "timestamp": now_iso(),
    }