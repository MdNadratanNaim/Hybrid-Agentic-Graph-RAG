import json
from llm.models import get_llm
from llm.prompts import get_prompt
from llm.parse_response import reasoning


def sanitizer_agent(content, evaluation_type, guard_verdict, context):
    """
    Return format:
        {
            "decision": "sanitized|escalate_block",
            "sanitized_content": "",
            "removed_elements": [
                { "category": "", "description": "" }
            ],
            "intent_preserved": True,
            "confidence": 0.0
        }
    """

    kwargs = {
        "content": content,
        "evaluation_type": evaluation_type,
        "guard_verdict": guard_verdict,
        "context": context, 
    }
    sanitizer_prompt = get_prompt("sanitizer", **kwargs)


    llm = get_llm("sanitizer")
    try:
        ai_message = llm.invoke(sanitizer_prompt)
        return json.loads(reasoning(ai_message).get("answer"))
    except:
        return{
                    "decision": "escalate_block",
                    "sanitized_content": None,
                    "removed_elements": [
                        { "category": "Error", "description": "Error while connecting to the server!" }
                    ],
                    "intent_preserved": False,
                    "confidence": 1.0
        }
