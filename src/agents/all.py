
def ingest_documents(files: list, options: dict) -> dict:

    """
    {
        "ingested": int,
        "doc_ids": list[str],
        "errors": list[str],
    }
    """

    return {
        "ingested": 4,
        "doc_ids": ["str", "df", "DF"],
        "errors": ["f", "df", "DF"],
    }


def rewrite_query(query: str, chat_history: list[dict], query_type: str) -> dict:

    """
        {
        "sub_questions": [
            {"question": str, "tool": "vector" | "web" | "sql" | "api"}, ...
        ],
    }
    """

    return {
        "sub_questions": [{"question": "str", "tool": "vector"}, ],
    }


def retrieve(sub_questions: list[dict], options: dict) -> dict:

    """
    {
        "candidates": [
            {"id": str, "text": str, "source": str, "score": float,
             "tool": str, "metadata": dict}, ...
        ],
    }
    """

    return {
        "candidates": [
            {"id": "str", "text": "str", "source": "str", "score": 0.8,
             "tool": "str", "metadata": dict()},
        ],
    }


def rerank(query: str, candidates: list[dict], top_n: int) -> dict:

    """
    {
        "reranked": [
            {"id": str, "text": str, "source": str, "score": float,
             "metadata": dict}, ...
        ],
    }
    """

    return {
        "reranked": [
            {"id": "str", "text": "str", "source": "str", "score": 0.8,
             "metadata": dict()},
        ],
    }


def summarize_chunks(chunks: list[dict]) -> dict:
    """
    {
        "summaries": [
            {"id": str, "summary": str, "source": str}, ...
        ],
    }
    """

    return {
        "summaries": [
            {"id": "str", "summary": "str", "source": "str"},
        ],
    }


def extract_graph(summaries: list[dict]) -> dict:

    """
    {
        "nodes": [{"id": str, "label": str, "type": str}, ...],
        "edges": [{"source": str, "target": str, "relation": str}, ...],
    }
    """

    return {
        "nodes": [{"id": "str", "label": "str", "type": "str"}, ],
        "edges": [{"source": "str", "target": "str", "relation": "str"}, ],
    }


def reason_over_evidence(query: str, summaries: list[dict], graph: dict | None) -> dict:
    """
    {
        "reasoning_trace": str,
        "contradictions": list[str],
        "key_facts": list[str],
    }
    """

    return {
        "reasoning_trace": "str",
        "contradictions": ["str", "df", "DF"],
        "key_facts": ["str", "df", "DF"],
    }


def check_sufficiency(query: str, reasoning_trace: dict) -> dict:
    """
    {
        "sufficient": bool,
        "action": "proceed" | "reformulate" | "re_retrieve",
        "missing_info": str | None,
    }
    """

    return {
        "sufficient": True,
        "action": "proceed",
        "missing_info": None,
    }


def generate_answer(query: str, reasoning_trace: dict | None, summaries: list[dict]) -> dict:
    """
    {
        "answer": str,
        "citations": [{"claim": str, "source": str}, ...],
        "uncited_claims": list[str],
        "confidence": float,            # 0-1
    }
    """

    return {
        "answer": "str",
        "citations": [{"claim": "str", "source": "str"}, ],
        "uncited_claims": ["str", "df", "DF"],
        "confidence": 0.8,
    }


def critic_check(answer: dict, summaries: list[dict]) -> dict:
    """
    {
        "passes": bool,
        "issues": list[str],
        "hallucination_risk": "low" | "medium" | "high",
    }
    """

    return {
        "passes": "bool",
        "issues": ["str", "df", "DF"],
        "hallucination_risk": "low",
    }


def output_guard(answer_text: str) -> dict:
    """
    {
        "safe": bool,
        "filtered_text": str | None,
        "reason": str | None,
    }
    """

    return {
        "safe": True,
        "filtered_text": "Naim",
        "reason": "Naim",
    }

