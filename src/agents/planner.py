import json
from llm.models import get_llm
from llm.parse_response import reasoning


def classify_query(query: str, chat_history: list[dict]) -> dict:

    """
    {
        "query_type": "direct_answer" | "single_hop" | "multi_hop" | "comparison" | "calculation",
        "needs_retrieval": bool,
        "confidence": float,            # 0-1, planner's confidence in the label
    }
    """

    try:
        ai_message = reasoning(get_llm("planner"))
        return json.loads(reasoning(ai_message).get("answer"))
    except:
        return None
