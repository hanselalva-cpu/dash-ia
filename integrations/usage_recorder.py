"""Punto de entrada para que tus apps registren consumo. Ver examples/record_usage_example.py."""

import logging
import time
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from models.schemas import Provider, Rate, UsageEvent, UsageUnit
from services.campaign_service import resolve_campaign_id
from services.pricing_service import calculate_cost

log = logging.getLogger(__name__)


class UsageRecorder:
    def __init__(self, usage_repo, rate_repo, api_key_repo=None, rates_ttl_seconds: int = 300):
        self.usage_repo = usage_repo
        self.rate_repo = rate_repo
        self.api_key_repo = api_key_repo
        self.rates_ttl_seconds = rates_ttl_seconds
        self._rates: list[Rate] = []
        self._rates_loaded_at = 0.0

    def _get_rates(self) -> list[Rate]:
        if time.monotonic() - self._rates_loaded_at > self.rates_ttl_seconds:
            self._rates = self.rate_repo.list()
            self._rates_loaded_at = time.monotonic()
        return self._rates

    def record(
        self,
        provider: Provider,
        model: str,
        quantities: dict[UsageUnit, int | float | Decimal],
        *,
        campaign_id: UUID | None = None,
        api_key_id: UUID | None = None,
        external_id: str | None = None,
        metadata: dict | None = None,
        occurred_at: datetime | None = None,
    ) -> UsageEvent:
        api_key = self.api_key_repo.get(api_key_id) if (self.api_key_repo and api_key_id) else None
        event = UsageEvent(
            provider=provider,
            model=model,
            quantities={UsageUnit(k): Decimal(str(v)) for k, v in quantities.items()},
            campaign_id=resolve_campaign_id(campaign_id, api_key),
            api_key_id=api_key_id,
            external_id=external_id,
            metadata=metadata or {},
            **({"occurred_at": occurred_at} if occurred_at else {}),
        )
        breakdown = calculate_cost(event, self._get_rates())
        if not breakdown.complete:
            # Se registra igual (no perder uso); el costo faltante se ve como tarifa pendiente.
            log.warning("Sin tarifa para %s/%s unidades=%s", provider, model, breakdown.missing_units)
            event.metadata["missing_rates"] = [str(u) for u in breakdown.missing_units]
        event.cost_usd = breakdown.total_usd
        return self.usage_repo.insert(event)
