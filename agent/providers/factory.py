"""
agent/providers/factory.py

Instancia o provider LLM conforme settings.LLM_PROVIDER.
"""

from config.settings import settings
from .base import LLMProvider


def get_provider() -> LLMProvider:
    provider = settings.LLM_PROVIDER.lower()

    if provider == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(settings.ANTHROPIC_API_KEY, settings.llm_model_resolved)

    if provider == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(settings.OPENAI_API_KEY, settings.llm_model_resolved)

    # default: gemini
    from .gemini import GeminiProvider
    return GeminiProvider(settings.GOOGLE_API_KEY, settings.llm_model_resolved)
