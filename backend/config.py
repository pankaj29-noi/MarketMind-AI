import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")

# DEMO_MODE: true | false | auto (default)
# - auto: use deterministic Lead extractor when GROQ key is missing/placeholder
# - true: prefer demo extractor unless a valid GROQ key is present (real LLM always wins)
# - false: never use demo extractor (require a valid GROQ key)
DEMO_MODE = (os.getenv("DEMO_MODE") or "auto").strip().lower()

_PLACEHOLDER_KEY_FRAGMENTS = (
    "your_groq_api_key",
    "your_gemini_api_key",
    "changeme",
    "replace_me",
    "xxx",
)


def _is_placeholder_key(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.strip().lower()
    if not lowered:
        return True
    return any(frag in lowered for frag in _PLACEHOLDER_KEY_FRAGMENTS)


def has_valid_llm_api_key() -> bool:
    """True when Groq is configured with a non-placeholder key."""
    return not _is_placeholder_key(GROQ_API_KEY)


def use_lead_demo_extraction() -> bool:
    """
    Whether Lead Intelligence should use the deterministic demo extractor.

    Real LLM path always wins when a valid GROQ_API_KEY is configured.
    """
    if has_valid_llm_api_key():
        return False
    if DEMO_MODE in ("0", "false", "no", "off"):
        return False
    # DEMO_MODE true/auto/empty + no valid key → demo extraction
    return True


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is missing or empty. "
        "Please ensure it is defined in your `.env` file in the project root directory, "
        "e.g. DATABASE_URL=postgresql://user:password@localhost:5432/autonomous_data_analyst"
    )

# Sandbox limits
SANDBOX_TIMEOUT_SECONDS = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "10"))
SANDBOX_MEMORY_LIMIT_MB = int(os.getenv("SANDBOX_MEMORY_LIMIT_MB", "256"))

def get_llm(temperature: float = 0.0):
    """
    Initializes and returns the primary ChatGroq model (Llama 3.3 70B),
    with a transparent provider-level fallback to Gemini if GOOGLE_API_KEY is present.
    """
    from langchain_groq import ChatGroq
    from langchain_google_genai import ChatGoogleGenerativeAI

    if _is_placeholder_key(GROQ_API_KEY):
        raise ValueError(
            "GROQ_API_KEY is missing or still set to a placeholder "
            "(e.g. your_groq_api_key). Set a real key in DataAgent-Pro/.env, "
            "or leave DEMO_MODE=auto/true so Lead Intelligence can use the "
            "deterministic demo extractor."
        )
    
    primary_llm = ChatGroq(
        api_key=GROQ_API_KEY,
        model_name="llama-3.3-70b-versatile",
        temperature=temperature
    )
    
    if GOOGLE_API_KEY and not _is_placeholder_key(GOOGLE_API_KEY):
        fallback_llm = ChatGoogleGenerativeAI(
            api_key=GOOGLE_API_KEY,
            model=GEMINI_FALLBACK_MODEL,
            temperature=temperature
        )
        return primary_llm.with_fallbacks([fallback_llm])
        
    return primary_llm
