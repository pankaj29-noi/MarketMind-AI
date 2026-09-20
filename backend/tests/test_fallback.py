"""Tests for LLM provider fallback configuration (aligned with key validation)."""
from unittest.mock import patch

from langchain_core.messages import AIMessage

from backend.config import get_llm

# Keys must pass has_valid_* checks (prefix + length).
FAKE_GROQ = "gsk_" + ("a" * 40)
FAKE_GEMINI = "AIza" + ("b" * 36)


def test_fallback_behavior_no_google_key():
    with patch("backend.config.GROQ_API_KEY", FAKE_GROQ), \
         patch("backend.config.GOOGLE_API_KEY", ""), \
         patch("backend.config.has_valid_groq_key", return_value=True), \
         patch("backend.config.has_valid_gemini_key", return_value=False):
        llm = get_llm()
        assert "ChatGroq" in type(llm).__name__
        assert not hasattr(llm, "fallbacks") or not getattr(llm, "fallbacks", None)


def test_fallback_configured():
    with patch("backend.config.GROQ_API_KEY", FAKE_GROQ), \
         patch("backend.config.GOOGLE_API_KEY", FAKE_GEMINI), \
         patch("backend.config.has_valid_groq_key", return_value=True), \
         patch("backend.config.has_valid_gemini_key", return_value=True):
        llm = get_llm()
        assert hasattr(llm, "fallbacks")
        assert len(llm.fallbacks) == 1
        assert "ChatGoogleGenerativeAI" in type(llm.fallbacks[0]).__name__


def test_fallback_success():
    with patch("backend.config.GROQ_API_KEY", FAKE_GROQ), \
         patch("backend.config.GOOGLE_API_KEY", FAKE_GEMINI), \
         patch("backend.config.has_valid_groq_key", return_value=True), \
         patch("backend.config.has_valid_gemini_key", return_value=True), \
         patch("langchain_groq.ChatGroq.invoke") as mock_groq_invoke, \
         patch("langchain_google_genai.ChatGoogleGenerativeAI.invoke") as mock_gemini_invoke:

        mock_groq_invoke.side_effect = Exception("Rate limit exceeded")
        mock_gemini_invoke.return_value = AIMessage(content="gemini response")

        llm = get_llm()
        result = llm.invoke("Test prompt")

        assert mock_groq_invoke.called
        assert mock_gemini_invoke.called
        assert result.content == "gemini response"


def test_primary_success():
    with patch("backend.config.GROQ_API_KEY", FAKE_GROQ), \
         patch("backend.config.GOOGLE_API_KEY", FAKE_GEMINI), \
         patch("backend.config.has_valid_groq_key", return_value=True), \
         patch("backend.config.has_valid_gemini_key", return_value=True), \
         patch("langchain_groq.ChatGroq.invoke") as mock_groq_invoke, \
         patch("langchain_google_genai.ChatGoogleGenerativeAI.invoke") as mock_gemini_invoke:

        mock_groq_invoke.return_value = AIMessage(content="groq response")

        llm = get_llm()
        result = llm.invoke("Test prompt")

        assert mock_groq_invoke.called
        assert not mock_gemini_invoke.called
        assert result.content == "groq response"
