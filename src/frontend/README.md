# Research Console — frontend

Streamlit frontend for the hybrid agentic + graph RAG pipeline. This module
only handles input, live progress, and result presentation — every agentic
call goes through `workflow_runner.py`, which imports directly from
`agents.all`.

## Expected project layout

```
project_root/
├── frontend/          ← this directory
│   ├── app.py
│   ├── components.py
│   ├── styles.py
│   ├── utils.py
│   ├── workflow_runner.py
│   ├── requirements.txt
│   └── assets/
│       └── logo.png   ← optional, shown in the header if present
└── src/
    └── agents/
        └── all.py      ← your pipeline's stage functions
```

`workflow_runner.py` adds `project_root/src` to `sys.path` automatically
(it looks two directories up from its own file). If your real layout puts
`src/` somewhere else, adjust `_SRC_DIR` at the top of `workflow_runner.py`.

## Run it

```
pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

## The `agents.all` contract

`workflow_runner.py` imports these 13 functions and documents the exact
return shape it expects from each one in its module docstring:

`guardrails` (the combined prompt_guard → safeguard_input → sanitizer_agent
cascade), `classify_query`, `ingest_documents`, `rewrite_query`, `retrieve`,
`rerank`, `summarize_chunks`, `extract_graph`, `reason_over_evidence`,
`check_sufficiency`, `generate_answer`, `critic_check`, `output_guard`.

`guardrails()`'s five possible `status` values are all handled explicitly:
`Allow` proceeds as-is, `Sanitize`/`Flagged` proceed with `sanitized_content`
and mark the run `flagged_for_review`, `Blocked` stops immediately with a
blocked result, and `Error` fails closed (stops with an error event rather
than passing an unchecked query through).

All reads of these return values go through `utils.safe_get`, so a missing
key won't crash the UI — but keeping the shapes as documented will keep the
signal-path rail, source cards, and knowledge-graph tab accurate.

## What's implemented

- **Real chat UI** — the conversation renders as `st.chat_message` bubbles
  (not a single-shot form-and-result layout). Each assistant bubble shows
  the answer plus an expander with the full Sources / Reasoning /
  Knowledge Graph / Logs detail for that turn.
- **Signal-path rail** — 13 nodes matching the architecture doc's numbering,
  live-updating as each stage runs, going gray when the router skips a
  stage. Rail + execution log now live in a single consolidated panel
  (one `st.empty()` placeholder, not several), and it's only mounted once
  a run has actually happened, instead of sitting there half-empty from
  page load.
- **Cascading safety gate** — one call to `guardrails()` covers
  prompt_guard → safeguard_input → sanitizer_agent. `Blocked` stops the
  run; `Sanitize`/`Flagged` continue with the cleaned query and surface a
  "Flagged for review" badge; `Error` fails closed.
- **Complexity routing table** — `workflow_runner.resolve_routing()`
  implements the direct_answer / single_hop / multi_hop / comparison /
  calculation table from the architecture doc.
- **Retrieval-source override** — six options: Auto, Vector DB only, Web
  search only, SQL only, API only, and "No retrieval — answer from
  model's own knowledge." No "Hybrid" or "Knowledge Graph" entries: hybrid
  dense+BM25 is always-on inside the vector tool itself (not a source you
  pick), and knowledge-graph retrieval isn't part of the current
  architecture — stage 7 extracts a per-query subgraph *from* retrieved
  evidence, it doesn't retrieve *from* a persistent graph index. The doc
  flags that as a separate, not-yet-built offline GraphRAG subsystem — say
  the word if you've since built it and want it added as a seventh option.
  The override forces `needs_retrieval` on/off and pins every
  sub-question's tool tag when a specific source is chosen.
- **Shared 3-iteration cap** — one counter covers both the planner's
  sufficiency-check loop and the critic's corrective loop, hard-capped at 3
  regardless of the UI slider. On cap-out, the run proceeds with a
  best-effort answer flagged `capped_out: true`.
- **Fixed light mode** — light/dark now overrides Streamlit's own theme
  CSS variables (`--primary-color`, `--background-color`,
  `--secondary-background-color`, `--text-color`) plus explicit
  `data-testid`-scoped rules for text areas, file uploader, selectbox,
  expanders, tabs, sliders, metrics, dataframes, and chat bubbles. The
  previous version only styled our own custom `<div>`s, so native widgets
  stayed on whichever theme the browser/server defaulted to — that's what
  was mixing text and background colors in light mode.
- **`HIDE_STREAMLIT_CHROME`** — a bool at the top of `app.py`. `True`
  (default) hides the "Deploy" button and the ⋮ overflow menu; set `False`
  to restore them.
- **1200px max content width**, centered.
- **Sidebar** — new session, theme toggle, this-session question history
  as compact chips, and disk-persisted saved runs (`frontend/.data/*.json`,
  created on first run) that open in a dedicated read-only viewer above
  the chat rather than overwriting it.

## Notes / open questions for you

- `ingest_documents` is called once per query if files are uploaded,
  before the retrieval loop — not re-run on corrective-loop iterations.
- The reformulate vs. re-retrieve distinction from `check_sufficiency`'s
  `action` field is logged but currently drives the same behavior (loop
  back through the rewriter). If your rewriter and retrieval need to be
  triggered independently, split `_retrieve_reason_cycle` in
  `workflow_runner.py` accordingly.
- On the stray-`<div>` report: I couldn't reproduce it directly (no
  Streamlit runtime in this sandbox), but the `stElementContainer` you
  found is Streamlit's own per-element wrapper, and the most likely cause
  was the old two-placeholder layout leaving an essentially-empty
  `st.empty()` mounted before any run happened. That's fixed by the
  single consolidated pipeline panel above. If you still see literal HTML
  text (not just an empty gap) after this update, tell me exactly what
  text is visible and I can pinpoint the specific `st.markdown` call.