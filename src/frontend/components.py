"""
components.py
--------------
All Streamlit render functions live here. Nothing in this file calls the
agent pipeline -- it only reads/writes st.session_state and renders.
"""

from __future__ import annotations

import html as html_lib

import streamlit as st

from utils import (
    ASSETS_DIR,
    RETRIEVAL_SOURCE_OPTIONS,
    STAGE_META,
    STAGE_ORDER,
    STATUS_DONE,
    STATUS_RUNNING,
    build_report_markdown,
    delete_saved_run,
    format_ms,
    new_session,
    safe_get,
    save_run,
    truncate,
)


# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------

def render_header() -> None:
    logo_path = ASSETS_DIR / "logo.png"
    if logo_path.exists():
        cols = st.columns([0.07, 0.93])
        with cols[0]:
            st.image(str(logo_path), width=42)
        with cols[1]:
            _render_header_text()
    else:
        _render_header_text()


def _render_header_text() -> None:
    st.markdown(
        """
        <div class="console-header">
            <div>
                <div class="console-eyebrow">Hybrid Agentic + Graph RAG</div>
                <p class="console-title">Research Console<span class="accent-dot">.</span></p>
                <p class="console-subtitle">
                    Ask a question. Watch it move through retrieval, reasoning, and review.
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("#### Session")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("＋ New", use_container_width=True):
                new_session()
                st.rerun()
        with c2:
            theme_label = "☀ Light" if st.session_state.theme == "dark" else "☾ Dark"
            if st.button(theme_label, use_container_width=True):
                st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
                st.rerun()

        st.caption(f"Session `{st.session_state.session_id}`")

        st.markdown("---")
        st.markdown("#### Conversation")
        history = st.session_state.get("chat_history", [])
        user_turns = [t for t in history if t.get("role") == "user"]
        if not user_turns:
            st.caption("No questions asked yet this session.")
        else:
            for turn in reversed(user_turns[-10:]):
                st.markdown(
                    f'<div class="history-chip">{html_lib.escape(truncate(turn.get("content", ""), 56))}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        st.markdown("#### Saved runs")
        saved_runs = st.session_state.get("saved_runs", [])
        if not saved_runs:
            st.caption("Runs you save will appear here.")
        else:
            for run in saved_runs[:10]:
                run_id = run.get("run_id", "unknown")
                st.markdown(
                    f'<div class="history-chip">{html_lib.escape(truncate(run.get("query", ""), 48))}</div>',
                    unsafe_allow_html=True,
                )
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("Open", key=f"load_{run_id}", use_container_width=True):
                        st.session_state.viewing_saved_run = run
                        st.rerun()
                with bc2:
                    if st.button("Delete", key=f"del_{run_id}", use_container_width=True):
                        delete_saved_run(run_id)
                        st.rerun()

        st.markdown("---")
        with st.expander("About this console"):
            st.markdown(
                "A 13-stage hybrid agentic + graph RAG pipeline: cascading "
                "safety gates, a complexity router that decides which stages "
                "actually run, hybrid retrieval with reranking, conditional "
                "graph extraction for multi-hop / comparison queries, and a "
                "critic loop with a shared 3-iteration cap."
            )


# --------------------------------------------------------------------------
# Query composer
# --------------------------------------------------------------------------

def render_query_panel() -> tuple[bool, str, list, dict]:
    with st.form("query_form", clear_on_submit=False):
        query = st.text_area(
            "Query",
            placeholder="Ask a question…",
            height=80,
            label_visibility="collapsed",
        )

        with st.expander("Advanced options"):
            files = st.file_uploader(
                "Upload documents (optional)",
                accept_multiple_files=True,
                help="Ingested before retrieval and searchable alongside the existing index.",
            )
            retrieval_source = st.selectbox("Retrieval source", options=RETRIEVAL_SOURCE_OPTIONS)

            c1, c2 = st.columns(2)
            with c1:
                top_k = st.slider("Top-K (post-rerank)", min_value=1, max_value=20, value=5)
                temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.2, step=0.05)
            with c2:
                confidence_threshold = st.slider(
                    "Confidence threshold", min_value=0.0, max_value=1.0, value=0.80, step=0.05
                )
                max_loops = st.slider(
                    "Max corrective loops", min_value=0, max_value=3, value=3,
                    help="Hard-capped at 3 regardless of this setting.",
                )

        _, btn_col = st.columns([4, 1])
        with btn_col:
            submitted = st.form_submit_button("Generate →", use_container_width=True)

    options = {
        "retrieval_source": retrieval_source,
        "top_k": top_k,
        "temperature": temperature,
        "confidence_threshold": confidence_threshold,
        "max_corrective_loops": max_loops,
    }
    return submitted, query, files or [], options


# --------------------------------------------------------------------------
# Pipeline panel (signal-path rail + collapsible log), rendered as ONE
# container so a live run doesn't leave multiple half-empty placeholders
# mounted in the page.
# --------------------------------------------------------------------------

def render_pipeline_panel(container, stage_status: dict[str, str], logs: list[dict], log_expanded: bool = False) -> None:
    with container.container():
        nodes_html = []
        for i, stage_id in enumerate(STAGE_ORDER):
            meta = STAGE_META[stage_id]
            status = stage_status.get(stage_id, "pending")
            line_class = status if status in (STATUS_DONE, STATUS_RUNNING) else ""
            line_html = "" if i == len(STAGE_ORDER) - 1 else f'<div class="signal-line {line_class}"></div>'
            # Built as one unbroken line (no embedded "\n") on purpose: a
            # multi-line f-string here, once joined with the other nodes,
            # produces whitespace-only lines at the seams -- and Streamlit's
            # markdown-to-HTML parser treats a blank line as the end of a
            # <div>-opened HTML block, silently dumping everything after the
            # first node as literal escaped text instead of rendering it.
            node_html = (
                '<div class="signal-node-wrap">'
                f'<div class="signal-node {status}" title="{html_lib.escape(meta["desc"])}">'
                f'<span class="signal-num">{meta["num"]:02d}</span>'
                f'<div class="signal-dot {status}"></div>'
                f'<span class="signal-code">{meta["code"]}</span>'
                "</div>"
                f"{line_html}"
                "</div>"
            )
            nodes_html.append(node_html)
        st.markdown(f'<div class="signal-rail">{"".join(nodes_html)}</div>', unsafe_allow_html=True)

        if logs:
            with st.expander("Execution log", expanded=log_expanded):
                render_stage_log(logs)


def render_stage_log(logs: list[dict]) -> None:
    if not logs:
        st.caption("No log entries yet.")
        return
    rows = []
    for entry in logs:
        stage = safe_get(entry, "stage", "?")
        detail = html_lib.escape(str(safe_get(entry, "detail", "")))
        ms = safe_get(entry, "ms", None)
        rows.append(
            f'<div class="stage-log-line"><span class="stage-code">{stage}</span>'
            f'{detail} <span class="latency">— {format_ms(ms)}</span></div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Confidence gauge
# --------------------------------------------------------------------------

def render_confidence_gauge(confidence: float) -> None:
    confidence = max(0.0, min(1.0, confidence or 0.0))
    deg = confidence * 360
    pct = f"{confidence:.0%}"
    st.markdown(
        f"""
        <div class="gauge-wrap">
            <div style="
                width:56px; height:56px; border-radius:50%;
                background: conic-gradient(var(--accent) {deg}deg, var(--panel-border) {deg}deg 360deg);
                display:flex; align-items:center; justify-content:center;">
                <div style="
                    width:40px; height:40px; border-radius:50%; background: var(--panel);
                    display:flex; align-items:center; justify-content:center;
                    font-family:'JetBrains Mono', monospace; font-size:0.68rem; color:var(--text);">
                    {pct}
                </div>
            </div>
            <div>
                <div class="gauge-value">{pct}</div>
                <div class="gauge-label">Confidence</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Source cards
# --------------------------------------------------------------------------

def render_source_card(source: dict) -> None:
    title = safe_get(source, "source", None) or safe_get(source, "id", "Unknown source")
    text = safe_get(source, "summary", None) or safe_get(source, "text", "")
    score = safe_get(source, "score", None)
    score_txt = f"score {score:.2f}" if isinstance(score, (int, float)) else ""
    st.markdown(
        f"""
        <div class="source-card">
            <div class="source-title">{html_lib.escape(str(title))}</div>
            <div class="source-meta">{score_txt}</div>
            <div class="source-body" style="margin-top:0.35rem; font-size:0.86rem;">{html_lib.escape(truncate(text, 400))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Knowledge graph
# --------------------------------------------------------------------------

def render_knowledge_graph(graph: dict | None) -> None:
    if not graph or not safe_get(graph, "nodes"):
        st.markdown(
            '<div class="empty-state">No graph extracted for this query — '
            'graph extraction only runs for multi-hop / comparison queries.</div>',
            unsafe_allow_html=True,
        )
        return

    nodes = safe_get(graph, "nodes", [])
    edges = safe_get(graph, "edges", [])

    try:
        import networkx as nx
        import plotly.graph_objects as go

        g = nx.DiGraph()
        for n in nodes:
            g.add_node(safe_get(n, "id"), label=safe_get(n, "label", safe_get(n, "id")))
        for e in edges:
            g.add_edge(safe_get(e, "source"), safe_get(e, "target"), relation=safe_get(e, "relation", ""))

        pos = nx.spring_layout(g, seed=7)

        edge_x, edge_y = [], []
        for u, v in g.edges():
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y, mode="lines",
            line=dict(width=1, color="rgba(156,163,173,0.5)"), hoverinfo="none",
        )

        node_x = [pos[n][0] for n in g.nodes()]
        node_y = [pos[n][1] for n in g.nodes()]
        node_labels = [g.nodes[n].get("label", n) for n in g.nodes()]

        node_trace = go.Scatter(
            x=node_x, y=node_y, mode="markers+text", text=node_labels,
            textposition="top center",
            marker=dict(size=16, color="#C98A3B", line=dict(width=1, color="#22262E")),
            hoverinfo="text",
        )

        fig = go.Figure(data=[edge_trace, node_trace])
        fig.update_layout(
            showlegend=False, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            height=380,
        )
        st.plotly_chart(fig, use_container_width=True)

    except ImportError:
        st.caption("Install `networkx` and `plotly` for a visual graph — showing a table instead.")
        st.dataframe(
            [{"source": safe_get(e, "source"), "relation": safe_get(e, "relation"),
              "target": safe_get(e, "target")} for e in edges],
            use_container_width=True, hide_index=True,
        )


# --------------------------------------------------------------------------
# Run detail (sources / reasoning / graph / logs) -- reused inside a chat
# bubble's expander AND in the saved-run viewer panel.
# --------------------------------------------------------------------------

def render_run_detail(run: dict, key_prefix: str = "run") -> None:
    if not run:
        st.markdown('<div class="empty-state">Nothing to show yet.</div>', unsafe_allow_html=True)
        return

    top = st.columns([0.7, 0.3])
    with top[0]:
        badges = []
        if run.get("capped_out"):
            badges.append('<span class="badge fail">Iteration cap reached — best-effort answer</span>')
        if run.get("blocked"):
            badges.append('<span class="badge fail">Blocked by input safety gate</span>')
        if run.get("flagged_for_review"):
            badges.append('<span class="badge accent">Flagged for review</span>')
        if badges:
            st.markdown(" ".join(badges), unsafe_allow_html=True)
    with top[1]:
        render_confidence_gauge(safe_get(run, "confidence", 0.0))

    tabs = st.tabs(["Sources", "Reasoning", "Knowledge Graph", "Logs"])

    with tabs[0]:
        sources = safe_get(run, "sources", [])
        if not sources:
            st.caption("No sources were retrieved for this query.")
        for src in sources:
            render_source_card(src)

    with tabs[1]:
        trace = safe_get(run, "reasoning_trace", None)
        if trace:
            st.write(trace)
        else:
            st.caption("No reasoning trace — this query didn't require the reasoner stage.")
        key_facts = safe_get(run, "key_facts", [])
        if key_facts:
            st.markdown("**Key facts**")
            for f in key_facts:
                st.markdown(f"- {f}")
        issues = safe_get(run, "critic_issues", [])
        if issues:
            st.markdown("**Critic notes**")
            for i in issues:
                st.markdown(f"- {i}")

    with tabs[2]:
        render_knowledge_graph(safe_get(run, "graph", None))

    with tabs[3]:
        c1, c2, c3 = st.columns(3)
        c1.metric("Iterations", f"{run.get('iterations_used', 0)} / {run.get('max_iterations', 0)}")
        c2.metric("Query type", run.get("query_type") or "—")
        c3.metric("Guard status", run.get("guard_status") or "—")
        render_stage_log(safe_get(run, "logs", []))

    footer_c1, footer_c2 = st.columns(2)
    with footer_c1:
        st.download_button(
            "Download report",
            data=build_report_markdown(run),
            file_name=f"{run.get('run_id', 'run')}.md",
            mime="text/markdown",
            key=f"{key_prefix}_download_{run.get('run_id', 'x')}",
            use_container_width=True,
        )
    with footer_c2:
        # save_run() runs as an on_click callback rather than inline after
        # the button check. Streamlit executes on_click callbacks BEFORE
        # the script reruns top-to-bottom, so by the time render_sidebar()
        # (called earlier in app.py's script order) runs on this same
        # click, st.session_state.saved_runs is already updated -- no
        # manual st.rerun() needed. (An inline call + st.rerun() looks
        # tempting but doesn't actually work: st.toast/st.success don't
        # reliably survive an immediately-following rerun, and a plain
        # st.rerun() would just show the sidebar its old state one click
        # later, which was the original bug.)
        save_clicked = st.button(
            "Save this run",
            key=f"{key_prefix}_save_{run.get('run_id', 'x')}",
            use_container_width=True,
            on_click=save_run,
            args=(run,),
        )
        if save_clicked:
            st.success("Saved.")


# --------------------------------------------------------------------------
# Chat transcript
# --------------------------------------------------------------------------

def render_chat_transcript(chat_history: list[dict]) -> None:
    if not chat_history:
        st.markdown(
            '<div class="empty-state">Ask a question below to get started.</div>',
            unsafe_allow_html=True,
        )
        return

    for i, turn in enumerate(chat_history):
        role = turn.get("role", "user")
        if role == "user":
            with st.chat_message("user"):
                st.write(turn.get("content", ""))
        else:
            avatar = "⚠️" if turn.get("is_error") else None
            with st.chat_message("assistant", avatar=avatar):
                st.write(turn.get("content", ""))
                run = turn.get("run")
                if run:
                    with st.expander("Details — sources, reasoning, graph, logs"):
                        render_run_detail(run, key_prefix=f"turn{i}")


def render_saved_run_viewer(run: dict) -> None:
    st.markdown("<hr class='console-divider'>", unsafe_allow_html=True)
    top = st.columns([0.85, 0.15])
    with top[0]:
        st.markdown(f"##### Viewing saved run — *{truncate(run.get('query', ''), 80)}*")
    with top[1]:
        if st.button("Close", use_container_width=True):
            st.session_state.viewing_saved_run = None
            st.rerun()
    st.write(safe_get(run, "answer", ""))
    render_run_detail(run, key_prefix="saved")