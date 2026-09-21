import logging
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Always load from project-root .env (DataAgent-Pro/.env), not CWD-dependent discovery.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
load_dotenv(_ENV_PATH, override=True)

# API Keys / models (re-read after dotenv)
GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip()
GOOGLE_API_KEY = (os.getenv("GOOGLE_API_KEY") or "").strip()
_RAW_GEMINI_MODEL = (os.getenv("GEMINI_FALLBACK_MODEL") or "gemini-2.0-flash").strip()
_RAW_GROQ_MODEL = (os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b").strip()

# DEMO_MODE: true | false | auto (default)
# - auto: deterministic demo paths only when no valid LLM provider is configured
# - true: same as auto when no valid key; real LLM always wins if a key is valid
# - false: never prefer deterministic demo paths for analytics/lead extraction
DEMO_MODE = (os.getenv("DEMO_MODE") or "auto").strip().lower()

_PLACEHOLDER_KEY_FRAGMENTS = (
    "your_groq_api_key",
    "your_gemini_api_key",
    "your_google_api_key",
    "changeme",
    "replace_me",
    "paste_your",
    "example_key",
)

# Groq retired llama-3.3-70b-versatile (Aug 2026). Prefer current production IDs.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
# Verified reachable 2026-09-21. Models that answer 404 are listed as retired below so
# the fallback chain never spends a round-trip on them.
GROQ_MODEL_CANDIDATES = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
)
GEMINI_MODEL_CANDIDATES = (
    "gemini-3.6-flash",
    "gemini-flash-latest",
)
_RETIRED_GROQ_MODELS = {
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama-3.1-70b-versatile",
    "qwen/qwen3.6-27b",
}
_RETIRED_GEMINI_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
}

# LLM call budget. A healthy provider answers in ~0.3-1.5s; anything beyond these
# bounds is retry/backoff against a degraded provider and must not block a request.
LLM_REQUEST_TIMEOUT_SECONDS = float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "20"))
LLM_CHAIN_DEADLINE_SECONDS = float(os.getenv("LLM_CHAIN_DEADLINE_SECONDS", "45"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "0"))


def _is_placeholder_key(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.strip().lower()
    if not lowered:
        return True
    if any(frag in lowered for frag in _PLACEHOLDER_KEY_FRAGMENTS):
        return True
    # Obvious fake / too-short tokens
    if lowered in {"xxx", "todo", "none", "null", "test"}:
        return True
    if len(lowered) < 20:
        return True
    return False


def _looks_like_api_key(value: str | None) -> bool:
    """True when a value is shaped like a secret, not a model id."""
    if not value:
        return False
    v = value.strip()
    if _is_placeholder_key(v):
        return False
    if v.startswith(("gsk_", "AIza", "AQ.", "ya29.", "sk-")):
        return True
    # Long opaque tokens without typical model naming
    if len(v) >= 32 and "gemini" not in v.lower() and "/" not in v:
        return True
    return False


def resolve_groq_model_name() -> str:
    raw = _RAW_GROQ_MODEL
    if not raw or _looks_like_api_key(raw) or _is_placeholder_key(raw):
        return DEFAULT_GROQ_MODEL
    if raw in _RETIRED_GROQ_MODELS:
        return DEFAULT_GROQ_MODEL
    return raw


def resolve_gemini_model_name() -> str:
    """GEMINI_FALLBACK_MODEL must be a model id, never an API key."""
    raw = _RAW_GEMINI_MODEL
    if not raw or _looks_like_api_key(raw) or _is_placeholder_key(raw):
        return DEFAULT_GEMINI_MODEL
    if not re.match(r"^[A-Za-z0-9._/-]+$", raw):
        return DEFAULT_GEMINI_MODEL
    if raw in _RETIRED_GEMINI_MODELS:
        return DEFAULT_GEMINI_MODEL
    return raw


GROQ_MODEL = resolve_groq_model_name()
GEMINI_FALLBACK_MODEL = resolve_gemini_model_name()


def has_valid_groq_key() -> bool:
    return not _is_placeholder_key(GROQ_API_KEY)


def has_valid_gemini_key() -> bool:
    return not _is_placeholder_key(GOOGLE_API_KEY)


def has_valid_llm_api_key() -> bool:
    """True when at least one LLM provider key is usable."""
    return has_valid_groq_key() or has_valid_gemini_key()


def use_lead_demo_extraction() -> bool:
    """
    Whether Lead Intelligence should use the deterministic demo extractor.

    Real LLM path always wins when any valid provider key is configured.
    """
    if has_valid_llm_api_key():
        return False
    if DEMO_MODE in ("0", "false", "no", "off"):
        return False
    return True


def sqlcoder_configured() -> bool:
    """True when local SQLCoder is enabled for NL→SQL (model may load lazily)."""
    try:
        from backend.services.sql.sqlcoder_service import sqlcoder_enabled

        return sqlcoder_enabled()
    except Exception:
        return False


def use_analytics_demo_fallback() -> bool:
    """
    Prefer deterministic analytics SQL only when no generative SQL path is available.

    DEMO_MODE=auto must NOT force fallback when Groq/Gemini or local SQLCoder is on.
    """
    if has_valid_llm_api_key():
        return False
    if sqlcoder_configured():
        return False
    if DEMO_MODE in ("0", "false", "no", "off"):
        return False
    return True


def preferred_analytics_provider() -> str:
    """Startup/runtime label: sqlcoder | groq | gemini | deterministic."""
    try:
        from backend.services.sql.sqlcoder_service import (
            sqlcoder_enabled,
            sqlcoder_prefer_over_api,
        )

        if sqlcoder_enabled() and sqlcoder_prefer_over_api():
            return "sqlcoder"
    except Exception:
        pass
    if has_valid_groq_key():
        return "groq"
    if has_valid_gemini_key():
        return "gemini"
    if sqlcoder_configured():
        return "sqlcoder"
    return "deterministic"


def log_provider_startup_diagnostics() -> None:
    """Safe startup diagnostics — never prints secrets."""
    print(f"GROQ_AVAILABLE={'true' if has_valid_groq_key() else 'false'}")
    print(f"GEMINI_AVAILABLE={'true' if has_valid_gemini_key() else 'false'}")
    print(f"SQLCODER_ENABLED={'true' if sqlcoder_configured() else 'false'}")
    print(f"DEMO_MODE={DEMO_MODE or 'auto'}")
    print(f"ANALYTICS_PROVIDER={preferred_analytics_provider()}")
    logger.info(
        "LLM providers: groq=%s gemini=%s sqlcoder=%s demo_mode=%s analytics_provider=%s "
        "groq_model=%s gemini_model=%s env=%s",
        has_valid_groq_key(),
        has_valid_gemini_key(),
        sqlcoder_configured(),
        DEMO_MODE,
        preferred_analytics_provider(),
        GROQ_MODEL,
        GEMINI_FALLBACK_MODEL,
        str(_ENV_PATH),
    )


DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if not DATABASE_URL:
    # Allow serverless / Vercel deploys without Postgres (DuckDB marketplace still works).
    logger.warning(
        "DATABASE_URL is not set — Postgres-backed features will be unavailable."
    )

# Sandbox limits
SANDBOX_TIMEOUT_SECONDS = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "10"))
SANDBOX_MEMORY_LIMIT_MB = int(os.getenv("SANDBOX_MEMORY_LIMIT_MB", "256"))

# CSV upload caps (protect free-tier memory)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))  # 15 MiB
MAX_UPLOAD_ROWS = int(os.getenv("MAX_UPLOAD_ROWS", "100000"))

# CORS — explicit origins only (never use "*" with allow_credentials=True).
# Override / extend via comma-separated CORS_ALLOWED_ORIGINS.
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "https://marketmind-ai-pankaj.vercel.app",
    "https://frontend-rho-nine-9ijte1vo4k.vercel.app",
    "https://marketmind-ai-pankajombishnoi-6423s-projects.vercel.app",
)


def get_cors_allowed_origins() -> list[str]:
    """Return deduped allowlist for FastAPI CORSMiddleware."""
    raw = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    origins: list[str] = []
    if raw:
        origins.extend(o.strip().rstrip("/") for o in raw.split(",") if o.strip())
    else:
        origins.extend(_DEFAULT_CORS_ORIGINS)
    # Preserve order, drop empties/dupes
    seen: set[str] = set()
    out: list[str] = []
    for o in origins:
        if o and o not in seen:
            seen.add(o)
            out.append(o)
    return out


CORS_ALLOWED_ORIGINS = get_cors_allowed_origins()


def get_runtime_data_root() -> Path:
    """Writable root for uploads/scratch (uses /tmp on Vercel)."""
    if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
        root = Path("/tmp/marketmind")
    else:
        root = _PROJECT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_scratch_root() -> Path:
    p = get_runtime_data_root() / "scratch"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_uploads_root() -> Path:
    p = get_runtime_data_root() / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _build_groq(temperature: float, model: str | None = None):
    from langchain_groq import ChatGroq

    return ChatGroq(
        api_key=GROQ_API_KEY,
        model_name=model or GROQ_MODEL,
        temperature=temperature,
        timeout=LLM_REQUEST_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


def _build_gemini(temperature: float, model: str | None = None):
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        api_key=GOOGLE_API_KEY,
        model=model or GEMINI_FALLBACK_MODEL,
        temperature=temperature,
        timeout=LLM_REQUEST_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


def get_llm(temperature: float = 0.0):
    """
    Returns the preferred LLM (Groq primary, Gemini fallback chain when both exist).

    Prefer invoke_llm() when caller needs accurate provider/model provenance.
    """
    if has_valid_groq_key() and has_valid_gemini_key():
        return _build_groq(temperature).with_fallbacks([_build_gemini(temperature)])
    if has_valid_groq_key():
        return _build_groq(temperature)
    if has_valid_gemini_key():
        return _build_gemini(temperature)
    raise ValueError(
        "No valid LLM API key configured. Set GROQ_API_KEY and/or GOOGLE_API_KEY in "
        f"{_ENV_PATH}, or leave DEMO_MODE=auto so deterministic demo paths can run."
    )


def invoke_llm(messages, temperature: float = 0.0) -> dict:
    """
    Invoke LLMs with explicit priority: Groq → Gemini (model candidates).

    Returns: {content, provider, model, analysis_source}
    analysis_source is 'groq' | 'gemini'.
    """
    from backend.services import llm_cache, llm_circuit
    from backend.utils.provider_errors import is_model_unavailable_error, is_rate_limit_error

    cache_key = llm_cache.make_key(messages, temperature) if llm_cache.is_cacheable(temperature) else None
    if cache_key:
        cached = llm_cache.get(cache_key)
        if cached:
            logger.info("LLM cache hit (model=%s)", cached.get("model"))
            cached["cache_hit"] = True
            return cached

    errors: list[str] = []
    deadline = time.monotonic() + LLM_CHAIN_DEADLINE_SECONDS

    def _dedupe(*models: str) -> list[str]:
        seen: list[str] = []
        for m in models:
            if m and m not in seen and m not in _RETIRED_GROQ_MODELS and m not in _RETIRED_GEMINI_MODELS:
                seen.append(m)
        return seen

    def _try(provider: str, models: list[str], build, source: str):
        if llm_circuit.is_open(provider):
            remaining = llm_circuit.cooldown_remaining(provider)
            errors.append(f"{source}:skipped, cooling down {remaining:.0f}s after a rate limit")
            logger.info("%s skipped: circuit open for another %.0fs.", provider, remaining)
            return None
        for model in models:
            if time.monotonic() >= deadline:
                errors.append(f"{source}[{model}]:skipped, chain deadline exceeded")
                logger.warning(
                    "LLM chain deadline (%.0fs) exceeded; skipping remaining candidates.",
                    LLM_CHAIN_DEADLINE_SECONDS,
                )
                return None
            try:
                resp = build(temperature, model=model).invoke(messages)
                content = getattr(resp, "content", None) or str(resp)
                logger.info("LLM invocation succeeded via %s model=%s", provider, model)
                payload = {
                    "content": content,
                    "provider": provider,
                    "model": model,
                    "analysis_source": source,
                }
                if cache_key:
                    llm_cache.set(cache_key, payload)
                llm_circuit.reset(provider)
                return dict(payload, cache_hit=False)
            except Exception as exc:
                errors.append(f"{source}[{model}]:{exc}")
                if is_rate_limit_error(str(exc)) and model == models[-1]:
                    # Every model for this provider is rate limited; stop paying for
                    # round-trips until the provider's own retry window elapses.
                    wait = llm_circuit.trip(provider, str(exc))
                    logger.warning(
                        "%s rate limited on all candidates; cooling down for %.0fs.",
                        provider,
                        wait,
                    )
                if is_model_unavailable_error(str(exc)):
                    logger.warning(
                        "%s model %s is unavailable (retired or no access) — consider removing it "
                        "from the candidate list.",
                        provider,
                        model,
                    )
                else:
                    logger.warning("%s model %s failed; trying next candidate.", provider, model)
        return None

    if has_valid_groq_key():
        result = _try("Groq", _dedupe(GROQ_MODEL, *GROQ_MODEL_CANDIDATES), _build_groq, "groq")
        if result:
            return result

    if has_valid_gemini_key():
        result = _try(
            "Gemini",
            _dedupe(GEMINI_FALLBACK_MODEL, *GEMINI_MODEL_CANDIDATES),
            _build_gemini,
            "gemini",
        )
        if result:
            return result

    detail = " | ".join(errors) if errors else "no providers configured"
    raise RuntimeError(f"All LLM providers failed: {detail}")
