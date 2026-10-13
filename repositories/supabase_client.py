from functools import lru_cache

from supabase import Client, create_client

from config.settings import get_settings


@lru_cache
def get_client() -> Client:
    settings = get_settings()
    if not settings.supabase_configured:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY no configurados (ver .env.example)")
    return create_client(settings.supabase_url, settings.supabase_key)
