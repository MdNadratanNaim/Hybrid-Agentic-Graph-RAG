from llm.models import get_llm
from llm.model_config import MODEL_CONFIGS


models = MODEL_CONFIGS.keys()
_NON_CHAT_KEYS = {"embedding", "reranker"}

for i in models:
    if i in _NON_CHAT_KEYS:
        continue

    print(f"\n\n######### {i} #########")
    system_prompt = "You are a helpful assistant."
    prompt = "Explain quantum computing in one sentence."
    messages = [
        ("system", system_prompt),
        ("human", prompt),
    ]

    if i == "prompt_guard":
        messages = prompt

    llm = get_llm(i)
    ai_message = llm.invoke(messages)
    print(ai_message)
