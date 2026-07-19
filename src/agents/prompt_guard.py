from llm.models import get_llm
from llm.parse_response import non_thinking


def prompt_guard(prompt: str) -> dict:
    """
    Return format:

        {"score": 0.95}
    """

    llm = get_llm("prompt_guard")
    try:
        ai_message = llm.invoke(prompt)
        score = float(non_thinking(ai_message).get("answer"))
        return {"score": score}

    except:
        return {"score": None}
