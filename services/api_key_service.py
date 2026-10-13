"""Registro de API keys sin guardar el secreto: solo hash (para identificar) y pista (últimos 4)."""

import hashlib
from uuid import UUID

from models.schemas import ApiKey, Provider


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def key_hint(raw_key: str) -> str:
    return f"…{raw_key[-4:]}" if len(raw_key) >= 4 else "…"


def build_api_key(provider: Provider, label: str, raw_key: str, default_campaign_id: UUID | None = None) -> ApiKey:
    return ApiKey(
        provider=provider,
        label=label,
        key_hint=key_hint(raw_key),
        key_hash=hash_key(raw_key),
        default_campaign_id=default_campaign_id,
    )
