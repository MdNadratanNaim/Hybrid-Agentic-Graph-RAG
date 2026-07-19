"""
Model configuration for the Hybrid (Agentic + Graph) RAG pipeline.
Updated from the original config to match the new 13-stage architecture.
"""

# Steps 9 (planner sufficiency check) and 12 (corrective loop) draw from the
# SAME iteration counter — do not budget them separately, or a single query
# can rack up 6+ round trips instead of the intended 3.
MAX_CORRECTIVE_ITERATIONS = 3


MODEL_CONFIGS = {

    # ── Step 1: Safety gate — input (cascading) ───────────────────────────
    # (a) always runs — cheap, fast classifier
    "prompt_guard": {
        "provider": "groq",
        "model": "meta-llama/llama-prompt-guard-2-86m",
        "temperature": 0.0,
        "model_kwargs": {
            "top_p": 1.0,
            "seed": 42,
        },
    },

    # (b) only invoked when prompt_guard is borderline/uncertain
    "safeguard_input": {
        "provider": "groq",
        "model": "openai/gpt-oss-safeguard-20b",
        "temperature": 0.0,
        "reasoning_effort": "low",
        "model_kwargs": {
            "top_p": 1.0,
            "seed": 42,
        },
    },

    "sanitizer": {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "temperature": 0.0,
        "reasoning_effort": "low",
        "model_kwargs": {
            "top_p": 1.0,
            "seed": 42,
        },
    },

    # ── Step 2 / 9: Planner — complexity router + sufficiency check ──────
    # Same model backs both roles (different prompts, same config).
    "planner": {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "temperature": 0.1,
        "model_kwargs": {
            "top_p": 1.0,
            "seed": 42,
        },
        "max_iterations": MAX_CORRECTIVE_ITERATIONS,
    },

    # ── Step 3: Query rewriter ────────────────────────────────────────────
    "query_rewriter": {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "temperature": 0.2,
        "model_kwargs": {
            "top_p": 1.0,
            "seed": 42,
        },
    },

    # ── Step 4: Retrieval — embedding model (gap in original design) ─────
    "embedding": {
        "provider": "openai",
        "model": "text-embedding-3-large",
        "model_kwargs": {
            "dimensions": 3072,
        },
    },

    # ── Step 5: Reranker ★ new stage ─────────────────────────────────────
    "reranker": {
        "provider": "cohere",            # swap to "self_hosted" for a BGE reranker
        "model": "rerank-v3.5",
        "top_n": 8,                      # candidates kept after rescoring
    },

    # ── Step 6: Summarizer — downgraded, highest call-volume node ────────
    "summarizer": {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "temperature": 0.2,
        "model_kwargs": {
            "top_p": 0.90,
            "seed": 42,
        },
        "batch_mode": "parallel",
    },

    # ── Step 7: Graph extractor — conditional ────────────────────────────
    "graph_extractor": {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "temperature": 0.0,
        "model_kwargs": {
            "top_p": 1.0,
            "seed": 42,
        },
        "runs_for": ["multi-hop", "comparison"],
    },

    # ── Step 8: Reasoner ──────────────────────────────────────────────────
    "reasoner": {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "temperature": 0.2,
        "model_kwargs": {
            "top_p": 0.95,
            "seed": 42,
        },
    },

    # ── Step 10: Answer generator ────────────────────────────────────────
    "answer_generator": {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "fallback_model": "qwen/qwen3.6-27b",
        "temperature": 0.4,
        "model_kwargs": {
            "top_p": 0.90,
            "seed": 42,
        },
        "require_citations": True,
    },

    # ── Step 11: Critic — unchanged (quality > throughput here) ──────────
    "critic": {
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
        "temperature": 0.0,
        "model_kwargs": {
            "top_p": 1.0,
            "seed": 42,
        },
    },

    # ── Step 13: Safety gate — output ────────────────────────────────────
    "safeguard_output": {
        "provider": "groq",
        "model": "openai/gpt-oss-safeguard-20b",
        "temperature": 0.0,
        "model_kwargs": {
            "top_p": 1.0,
            "seed": 42,
        },
        "bring_your_own_policy": True,
    },
}


# ── Complexity routing table (architecture §3) ────────────────────────────
# Governs which stages actually fire for a given planner classification.
STAGE_ROUTING = {
    "direct_answer": {
        "query_rewriter": False,
        "retrieval": False,
        "reranker": False,
        "summarizer": False,
        "graph_extractor": False,
        "reasoner": False,
        "corrective_loop": False,
    },
    "single-hop": {
        "query_rewriter": "light",
        "retrieval": True,
        "reranker": True,
        "summarizer": True,
        "graph_extractor": False,
        "reasoner": "light",
        "corrective_loop": True,
    },
    "multi-hop": {
        "query_rewriter": True,
        "retrieval": True,
        "reranker": True,
        "summarizer": True,
        "graph_extractor": True,
        "reasoner": True,
        "corrective_loop": True,
    },
    "comparison": {
        "query_rewriter": True,
        "retrieval": True,
        "reranker": True,
        "summarizer": True,
        "graph_extractor": True,
        "reasoner": True,
        "corrective_loop": True,
    },
    "calculation": {
        "query_rewriter": "extract_operands",
        "retrieval": "as_needed",
        "reranker": "as_needed",
        "summarizer": "optional",
        "graph_extractor": False,
        "reasoner": True,
        "corrective_loop": True,
    },
}
