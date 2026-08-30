"""Shared helpers for detecting LLM provider failures."""
from __future__ import annotations


def is_provider_auth_or_config_error(error_message: str) -> bool:
    """True when the LLM provider rejected the request due to auth/config (not rate limit)."""
    text = (error_message or "").lower()
    markers = (
        "invalid api key",
        "incorrect api key",
        "unauthorized",
        "401",
        "403",
        "api key not set",
        "api_key",
        "authentication",
        "permission denied",
        "api key is invalid",
        "your_groq_api_key",
        "your_gemini_api_key",
        "all llm providers failed",
        "no valid llm",
    )
    return any(m in text for m in markers)


def provider_error_user_message(error_message: str) -> str:
    """Safe, actionable message for the System Failure Report UI."""
    if is_provider_auth_or_config_error(error_message):
        return (
            "LLM provider authentication failed. Set a valid GROQ_API_KEY in DataAgent-Pro/.env "
            "(copy from .env.example), then restart the backend. Optional: set GOOGLE_API_KEY for Gemini fallback."
        )
    text = (error_message or "").lower()
    if "429" in text or "rate limit" in text or "resource_exhausted" in text:
        return "LLM provider rate limit reached. Wait a moment and retry, or switch providers."
    return "The LLM provider could not complete this request. Check API keys and provider status."
