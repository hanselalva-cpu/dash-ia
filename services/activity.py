"""Actividad de recursos: activo = tuvo gasto en los últimos N días."""

from models.schemas import UsageEvent
from services.campaign_service import resource_key_of

ACTIVITY_DAYS = 15


def active_resource_keys(events: list[UsageEvent]) -> set[tuple[str, str]]:
    """(proveedor, resource_key) de los recursos con algún gasto > 0 entre los eventos dados."""
    return {(str(e.provider), key) for e in events
            if float(e.cost_usd or 0) > 0 and (key := resource_key_of(e)) is not None}
