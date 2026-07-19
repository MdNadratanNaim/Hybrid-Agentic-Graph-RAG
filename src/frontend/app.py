"""
app.py
------
Entry point. Run with:  streamlit run frontend/app.py

Keeps the UI purely responsible for input, live progress visualization,
and result presentation. All agentic behavior lives in `agents.all`,
called by `workflow_runner.run_pipeline`.
"""

from __future__ import annotations

import time

import streamlit as st

from components import (
    render_chat_transcript,
    render_header,
    render_pipeline_panel,
    render_query_panel,
    render_saved_run_viewer,
    render_sidebar,
)
from styles import inject_css
from utils import STAGE_ORDER, init_session_state, reset_stage_status
from workflow_runner import run_pipeline

# Max width for the page
PAGE_MAX_WIDTH_PX = 1200

st.set_page_config(
    page_title="Research Console — Hybrid Agentic + Graph RAG",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()
inject_css(st.session_state.theme)

_chrome_css = f"""
<style>
.block-container {{
    max-width: {PAGE_MAX_WIDTH_PX}px;
    margin: 0 auto;
    padding-top: 1.6rem;
}}

.stAppDeployButton{{
    display: none;
}}

#MainMenu {{
    visibility: hidden;
}}
</style>
"""
st.markdown(_chrome_css, unsafe_allow_html=True)


render_sidebar()
render_header()

if st.session_state.viewing_saved_run:
    render_saved_run_viewer(st.session_state.viewing_saved_run)
else:
    render_chat_transcript(st.session_state.chat_history)

pipeline_placeholder = st.empty()
if st.session_state.run_logs:
    render_pipeline_panel(pipeline_placeholder, st.session_state.stage_status, st.session_state.run_logs)

st.markdown("<div style='height: 0.75rem'></div>", unsafe_allow_html=True)
submitted, query, files, options = render_query_panel()

if submitted:
    if not query or not query.strip():
        st.warning("Enter a question before generating an answer.")
    else:
        reset_stage_status()
        st.session_state.is_running = True
        st.session_state.viewing_saved_run = None
        st.session_state.chat_history.append(
            {"role": "user", "content": query, "ts": time.time()}
        )

        live_logs: list[dict] = []
        final_result = None
        error_message = None

        with st.spinner("Running pipeline…"):
            for event in run_pipeline(query, files, options, st.session_state.chat_history):
                etype = event.get("type")

                if etype == "stage":
                    stage_id = event.get("stage")
                    status = event.get("status")
                    if stage_id in STAGE_ORDER:
                        st.session_state.stage_status[stage_id] = status
                    live_logs.append(event)
                    st.session_state.run_logs = live_logs
                    render_pipeline_panel(
                        pipeline_placeholder, st.session_state.stage_status, live_logs, log_expanded=True
                    )

                elif etype == "final":
                    final_result = event.get("result")

                elif etype == "error":
                    error_message = event.get("message")

        st.session_state.is_running = False

        if error_message:
            # A transient st.error() here would be wiped by the st.rerun()
            # below before most users could read it -- that rerun is
            # required regardless (the user's turn was already appended to
            # chat_history above, and render_chat_transcript ran *before*
            # that append this pass, so it needs a rerun to show it at
            # all). Appending the error as its own turn means it persists
            # through the rerun instead of flashing and disappearing.
            st.session_state.chat_history.append(
                {
                    "role": "assistant",
                    "content": f"⚠️ Pipeline stopped: {error_message}",
                    "ts": time.time(),
                    "run": None,
                    "is_error": True,
                }
            )
        elif final_result:
            st.session_state.current_run = final_result
            st.session_state.chat_history.append(
                {
                    "role": "assistant",
                    "content": final_result.get("answer", ""),
                    "ts": time.time(),
                    "run": final_result,
                }
            )
        st.rerun()