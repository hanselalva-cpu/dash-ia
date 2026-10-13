from functools import lru_cache

from supabase import Client, create_client

from config.settings import get_settings


@lru_cache
def _client(url: str, key: str) -> Client:
    return create_client(url, key)


def get_client() -> Client:
    """Un cliente por (URL, key): si cambian en Secrets/.env se crea uno nuevo."""
    settings = get_settings()
    if not settings.supabase_configured:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY no configurados (ver .env.example)")
    return _client(settings.supabase_url, settings.supabase_key)
