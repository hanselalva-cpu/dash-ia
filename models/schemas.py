"""Modelos de dominio compartidos por servicios, repositorios e integraciones."""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class Provider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPGRAM = "deepgram"
    ELEVENLABS = "elevenlabs"


class UsageUnit(StrEnum):
    INPUT_TOKENS = "input_tokens"
    OUTPUT_TOKENS = "output_tokens"
    CACHED_INPUT_TOKENS = "cached_input_tokens"
    CACHE_WRITE_TOKENS = "cache_write_tokens"
    AUDIO_SECONDS = "audio_seconds"
    CHARACTERS = "characters"
    REQUESTS = "requests"


class UsageSource(StrEnum):
    SDK = "sdk"
    IMPORT = "import"
    PROVIDER_SYNC = "provider_sync"  # costo reportado por la API del proveedor


class Campaign(BaseModel):
    id: UUID | None = None
    name: str
    client: str | None = None
    monthly_budget_usd: Decimal | None = None  # obsoleto: el tope vive en budget_alerts
    status: str = "active"
    created_at: datetime | None = None  # fija el color de la campaña en las gráficas


class ApiKey(BaseModel):
    id: UUID | None = None
    provider: Provider
    label: str
    key_hint: str
    key_hash: str
    default_campaign_id: UUID | None = None
    active: bool = True


class Rate(BaseModel):
    """Precio de `price_usd` por cada `per_units` unidades (ej. 0.15 USD por 1_000_000 tokens)."""

    provider: Provider
    model: str  # "*" = aplica a cualquier modelo del proveedor
    unit: UsageUnit
    price_usd: Decimal
    per_units: int = 1
    effective_from: date
    effective_to: date | None = None  # exclusivo


class UsageEvent(BaseModel):
    id: UUID | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider: Provider
    model: str
    quantities: dict[UsageUnit, Decimal] = Field(default_factory=dict)
    cost_usd: Decimal | None = None
    campaign_id: UUID | None = None
    api_key_id: UUID | None = None
    source: UsageSource = UsageSource.SDK
    external_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class BudgetAlert(BaseModel):
    """Tope mensual de gasto de una campaña, en la moneda capturada."""

    campaign_id: UUID
    limit_amount: Decimal
    currency: str = "USD"
    warning_pct: Decimal = Decimal("0.8")
    active: bool = True


class ResourceKind(StrEnum):
    API_KEY = "api_key"
    AGENT = "agent"


class ProviderResource(BaseModel):
    """API key o agente de un proveedor, asignable a una campaña."""

    id: UUID | None = None
    provider: Provider
    kind: ResourceKind
    resource_key: str
    name: str
    provider_ref: str | None = None
    group_name: str | None = None
    campaign_id: UUID | None = None
    active: bool = True


class ProviderInvoice(BaseModel):
    provider: Provider
    period_month: date  # primer día del mes
    amount_usd: Decimal
