import json
from llm.models import get_llm
from llm.prompts import get_prompt
from llm.parse_response import reasoning


def safeguard_input(content: str, context: str, evaluation_type: str) -> dict:
    """
    Return format:

        {
            "risk_level": "SAFE" | "LOW_RISK" | "MEDIUM_RISK" | "HIGH_RISK",
            "categories": [],
            "reason": "",
            "recommended_action": "allow" | "flag" | "route_to_sanitizer" | "block",
            "detected_entities": {
                "secret_types": [],
                "encoded_payloads": [],
                "injection_patterns": []
            },
            "evidence": [
                { "excerpt": "", "note": "" }
            ],
            "confidence": 0.0
        }
    """

    kwargs = {
        "content": content, 
        "context": context, 
        "evaluation_type": evaluation_type
    }
    safeguard_prompt = get_prompt("safeguard_input", **kwargs)


    llm = get_llm("safeguard_input")
    try:
        ai_message = llm.invoke(safeguard_prompt)
        return json.loads(reasoning(ai_message).get("answer"))
    except:
        return{
                    "risk_level": "HIGH_RISK",
                    "categories": ["Error"],
                    "reason": "Error while connecting to the server!",
                    "recommended_action": "block",
                    "detected_entities": {
                        "secret_types": [],
                        "encoded_payloads": [],
                        "injection_patterns": []
                    },
                    "evidence": [
                        { "excerpt": "", "note": "" }
                    ],
                    "confidence": 1.0
        }


def safeguard_output(content: str, context: str, evaluation_type: str) -> dict:
    """
    Return format:

        {
            "risk_level": "SAFE" | "LOW_RISK" | "MEDIUM_RISK" | "HIGH_RISK",
            "categories": [],
            "reason": "",
            "recommended_action": "allow" | "flag" | "route_to_sanitizer" | "block",
            "redaction_spans": [
                { "anchor": "", "type": "" }
            ],
            "confidence": 0.0
        }
    """

    kwargs = {
        "content": content, 
        "context": context, 
        "evaluation_type": evaluation_type
    }
    safeguard_prompt = get_prompt("safeguard_output", **kwargs)


    llm = get_llm("safeguard_output")
    try:
        ai_message = llm.invoke(safeguard_prompt)
        return json.loads(reasoning(ai_message).get("answer"))
    except:
        return {
            "risk_level": "HIGH_RISK",
            "categories": ["Error"],
            "reason": "Error while connecting to the server!",
            "recommended_action": "block",
            "redaction_spans": [
                { "anchor": "", "type": "" }
            ],
            "confidence": 1.0
        }
