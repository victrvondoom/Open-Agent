from __future__ import annotations

from app.core.config import get_settings
from app.rag.retrieval.factory import get_vector_store, validate_vector_store_startup


def run_startup_checks() -> None:
    settings = get_settings()
    if settings.environment == "test":
        return
    if not settings.disable_external_llm:
        provider = (settings.llm_provider or "gemini").strip().lower()
        if provider == "nvidia" and not settings.nvidia_api_key:
            raise RuntimeError("NVIDIA_API_KEY must be configured in environment or .env file when LLM_PROVIDER=nvidia.")
        if provider == "gemini" and not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY must be configured in environment or .env file.")
    validate_vector_store_startup()
    from app.knowledge_graph.factory import validate_graph_store_startup

    validate_graph_store_startup()
    if settings.environment == "production" and not settings.supabase_jwt_secret:
        raise RuntimeError("Production requires SUPABASE_JWT_SECRET for JWT verification")


async def collect_health_status() -> dict:
    settings = get_settings()
    vector = get_vector_store().health_check()
    from app.knowledge_graph.factory import get_graph_store

    graph = get_graph_store().health_check()
    redis_status = _redis_health(settings.redis_url)
    from app.llm.service import get_llm_provider

    llm_health = get_llm_provider().health_check()
    provider = (settings.llm_provider or "gemini").strip().lower()
    llm_key_status = {
        "status": "disabled"
        if settings.disable_external_llm
        else (
            "configured"
            if (provider == "nvidia" and settings.nvidia_api_key)
            or (provider == "gemini" and settings.gemini_api_key)
            else "missing_key"
        ),
        "provider": provider,
    }
    return {
        "vector_store": vector,
        "graph_store": graph,
        "supabase": {
            "status": "configured" if settings.supabase_url and settings.supabase_service_role_key else "not_configured",
            "url": settings.supabase_url or "",
        },
        "llm_provider": llm_key_status,
        "llm": llm_health,
        "redis": redis_status,
        "web_search": {
            "status": "configured" if settings.tavily_api_key else "not_configured",
        },
    }


def _redis_health(redis_url: str) -> dict:
    from app.services.cache import _redact_url
    from app.core.config import get_settings

    settings = get_settings()
    redacted = _redact_url(redis_url) if redis_url else ""
    if not redis_url or not settings.cache_enabled:
        return {"status": "disabled", "url": redacted, "info": "Local in-memory fallback active"}

    try:
        import redis

        client = redis.from_url(redis_url, socket_connect_timeout=0.5)
        client.ping()
        return {"status": "ready", "url": redacted}
    except Exception:
        if settings.environment == "development":
            return {"status": "disabled", "url": redacted, "info": "Local dev in-memory fallback active"}
        return {"status": "unreachable", "url": redacted, "error": "Redis server unreachable"}
