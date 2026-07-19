"""
Centralized LLM factory and model registry.
"""

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from llm.model_config import MODEL_CONFIGS


load_dotenv()
_NON_CHAT_KEYS = {"embedding", "reranker"}


class LLMFactory:
    """
    Creates configured chat-model instances.

    For non-chat entries (embedding, reranker) use
    LLMFactory.create_embedding() / LLMFactory.create_reranker() instead.
    """

    @staticmethod
    def create(model_key: str):
        if model_key in _NON_CHAT_KEYS:
            raise ValueError(
                f"'{model_key}' is not a chat model — use "
                f"LLMFactory.create_embedding() or LLMFactory.create_reranker()."
            )

        config = MODEL_CONFIGS.get(model_key)
        if not config:
            raise ValueError(f"Unknown model key: {model_key}")

        provider = config.get("provider")
        if provider != "groq":
            raise ValueError(f"Unsupported chat provider: {provider}")

        model_kwargs = config.get("model_kwargs", {})
        llm = ChatGroq(
            model=config.get("model"),
            temperature=config.get("temperature"),
            model_kwargs=model_kwargs,
        )

        # answer_generator (and any future entry) can declare a same-provider
        # fallback_model. Wire it up via LangChain's built-in fallback support
        # so callers don't need to special-case it at the call site.
        fallback_model = config.get("fallback_model")
        if fallback_model:
            fallback_llm = ChatGroq(
                model=fallback_model,
                temperature=config.get("temperature"),
                model_kwargs=model_kwargs,
            )
            llm = llm.with_fallbacks([fallback_llm])

        return llm

    @staticmethod
    def create_embedding(model_key: str = "embedding"):
        config = MODEL_CONFIGS.get(model_key)
        if not config:
            raise ValueError(f"Unknown model key: {model_key}")

        provider = config.get("provider")
        if provider == "openai":
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                model=config.get("model"),
                **config.get("model_kwargs", {}),
            )

        raise ValueError(f"Unsupported embedding provider: {provider}")

    @staticmethod
    def create_reranker(model_key: str = "reranker"):
        config = MODEL_CONFIGS.get(model_key)
        if not config:
            raise ValueError(f"Unknown model key: {model_key}")

        provider = config.get("provider")
        if provider == "cohere":
            from langchain_cohere import CohereRerank

            return CohereRerank(
                model=config.get("model"),
                top_n=config.get("top_n"),
            )

        raise ValueError(f"Unsupported reranker provider: {provider}")


def get_llm(model_key: str):
    return LLMFactory.create(model_key)


def get_embedding_model(model_key: str = "embedding"):
    return LLMFactory.create_embedding(model_key)


def get_reranker(model_key: str = "reranker"):
    return LLMFactory.create_reranker(model_key)
