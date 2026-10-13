"""Reglas de campañas: atribución de uso a campaña."""

from uuid import UUID

from models.schemas import ApiKey, Provider, ProviderResource, UsageEvent

# Campo de usage_events.metadata que identifica al recurso, por proveedor.
RESOURCE_KEY_FIELD = {
    Provider.OPENAI: "openai_api_key_id",
    Provider.DEEPGRAM: "deepgram_api_key_id",
    Provider.ELEVENLABS: "agent_name",
}


def resolve_campaign_id(explicit_campaign_id: UUID | None, api_key: ApiKey | None) -> UUID | None:
    """Prioridad: campaña explícita del evento > campaña por defecto de la API key > sin atribuir."""
    if explicit_campaign_id is not None:
        return explicit_campaign_id
    if api_key is not None:
        return api_key.default_campaign_id
    return None


def resource_key_of(event: UsageEvent) -> str | None:
    field = RESOURCE_KEY_FIELD.get(event.provider)
    return event.metadata.get(field) if field else None


def build_resource_campaign_map(resources: list[ProviderResource]) -> dict[tuple[str, str], UUID]:
    return {(str(r.provider), r.resource_key): r.campaign_id for r in resources if r.campaign_id}


def attribute_campaigns(events: list[UsageEvent], resources: list[ProviderResource]) -> list[UsageEvent]:
    """Asigna campaign_id a eventos sin campaña según el catálogo de recursos (retroactivo, no persiste)."""
    mapping = build_resource_campaign_map(resources)
    for event in events:
        if event.campaign_id is None:
            key = resource_key_of(event)
            if key is not None:
                event.campaign_id = mapping.get((str(event.provider), key))
    return events
