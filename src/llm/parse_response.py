import re


def thinking(response: dict) -> dict:
    """
    thinking_models = ["sanitizer", "critic"]
    """

    content = response.content
    pattern = r"<think>(.*?)</think>(.*)"
    search = re.search(pattern, content, re.DOTALL)
    
    thinking = search.group(1).strip()
    answer = search.group(2).strip()

    return {
        "thinking": thinking,
        "answer": answer,
    }


def reasoning(response: dict) -> dict:
    """
    reasoning_models = ["safeguard_input", "planner", "query_rewriter", "summarizer", "graph_extractor", "reasoner", "answer_generator", "safeguard_output"]
    """

    answer = response.content
    thinking = response.additional_kwargs.get("reasoning_content", "")

    return {
        "thinking": thinking,
        "answer": answer,
    }


def non_thinking(response: dict) -> dict:
    answer = response.content

    return {
        "answer": answer
    }
