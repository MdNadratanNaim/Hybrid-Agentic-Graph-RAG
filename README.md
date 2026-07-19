# On Devlopment


## Outline

```
          USER INPUT
              │
              ▼
┌──────────────────────────────────┐
│ 1. SAFETY GATES                  │
│    prompt_guard (input)          │     (Unsafe)
│       - llama-prompt-guard-2-86m │ ─────────────────► block / sanitise
│    safeguard (jailbreak)         │                               │
│       - gpt-oss-safeguard-20b    │                               │
└─────────────┬────────────────────┘                               │
              │ (safe)                                             ▼
              ▼                                              Sanitizer Agent
┌─────────────────────────────┐                                    │
│ 2. PLANNER                  │                                    │
│    qwen3-32b (temp 0.1)     │                                    ▼
│  - Analyses intent          │ ◄────────────────────────── Sanitized Query
│    direct_answer, single-   │
│    hop, multi-hop,          │
│    comparison, calculation  │
└─────────────┬───────────────┘
              │
        ┌─────▼─────┐
        │ Retrieval │
        │ needed ?  │
        └─────┬─────┘
          No  │  Yes
              ▼
┌─────────────────────────────┐
│ 3. QUERY REWRITER           │
│    llama-3.1-8b (temp 0.2)  │
│  - Breaks complex query     │
│    into sub‑questions       │
│  - Optimises for search     │
│  - Uses chat history        │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│ 4. RETRIEVAL (tool, not an LLM agent)   │
│    - Vector DB, web search, SQL, API    │
│    - Metadata filtering                 │
│    - Returns top‑k chunks               │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 5. SUMMARIZER               │
│    qwen3.6-27b (temp 0.2)   │
│  - Condenses each retrieved │
│    chunk to essential facts │
│  - Removes noise/boilerplate│
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 6. GRAPH EXTRACTOR          │
│    llama-3.1-8b (temp 0.0)  │
│  - Extracts entities,       │
│    relationships, claims    │
│  - Builds structured        │
│    knowledge sub‑graph      │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 7. REASONER                 │
│    qwen3-32b (temp 0.2)     │
│  - Reads summarised text    │
│    + extracted graph        │
│  - Connects facts, resolves │
│    contradictions           │
│  - Produces a structured    │
│    reasoning trace          │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 8. PLANNER (again)          │
│  - Evaluates if the reasoner│
│    output fully answers the │
│    query                    │
│  - Decides:                 │
│    • Sufficient → proceed   │
│    • Missing info → reform. │
│      (back to step 3)       │
│    • Need different source  │
│      (back to step 4)       │
└─────────────┬───────────────┘
              │ (sufficient)
              ▼
┌─────────────────────────────┐
│ 9. ANSWER GENERATOR         │
│    llama-3.3-70b (temp 0.4) │
│  - Synthesises final answer │
│  - Uses reasoning trace +   │
│    summarised sources       │
│  - Cites sources clearly    │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 10. CRITIC                  │
│     qwen3.6-27b (temp 0.0)  │
│  - Hallucination check      │
│  - Factual consistency with │
│    retrieved evidence       │
│  - Completeness & logic     │
└─────────────┬───────────────┘
              │
        ┌─────▼─────┐
        │ Passes ?  │
        └─────┬─────┘
          No  │  Yes
              ▼
┌─────────────────────────────┐
│ 11. CORRECTIVE LOOP         │
│  - Critic flags missing     │
│    facts or hallucination   │
│  - Planner receives feedback│
│  - Re‑plans: re‑retrieve,   │
│    refine query, etc.       │
│  (back to step 3 or 4)      │
└─────────────────────────────┘
              │ (pass)
              ▼
┌─────────────────────────────┐
│ 12. SAFEGUARD (output)      │
│     openai/gpt-oss-20b      │
│  - Checks final answer for  │
│    harmful / policy content │
└─────────────┬───────────────┘
              │
              ▼
         FINAL ANSWER
      (with citations & confidence)
```

## Available models
- llama-3.1-8b-instant
- llama-3.3-70b-versatile
- meta-llama/llama-4-scout-17b-16e-instruct
- meta-llama/llama-prompt-guard-2-22m
- meta-llama/llama-prompt-guard-2-86m
- openai/gpt-oss-120b
- openai/gpt-oss-20b
- openai/gpt-oss-safeguard-20b
- qwen/qwen3-32b
- qwen/qwen3.6-27b
- whisper-large-v3
- whisper-large-v3-turbo