from datetime import date
from decimal import Decimal

from supabase import Client

from models.schemas import Provider, Rate, UsageUnit

TABLE = "rates"

# Precios ILUSTRATIVOS para modo demo. Verificar contra la página de precios de cada proveedor
# antes de cargarlos en `rates` de producción.
_D = date(2026, 1, 1)
DEMO_RATES = [
    Rate(provider=Provider.OPENAI, model="gpt-4o-mini", unit=UsageUnit.INPUT_TOKENS,
         price_usd=Decimal("0.15"), per_units=1_000_000, effective_from=_D),
    Rate(provider=Provider.OPENAI, model="gpt-4o-mini", unit=UsageUnit.OUTPUT_TOKENS,
         price_usd=Decimal("0.60"), per_units=1_000_000, effective_from=_D),
    Rate(provider=Provider.ANTHROPIC, model="claude-haiku-5-5", unit=UsageUnit.INPUT_TOKENS,
         price_usd=Decimal("1.00"), per_units=1_000_000, effective_from=_D),
    Rate(provider=Provider.ANTHROPIC, model="claude-haiku-5-5", unit=UsageUnit.OUTPUT_TOKENS,
         price_usd=Decimal("5.00"), per_units=1_000_000, effective_from=_D),
    Rate(provider=Provider.DEEPGRAM, model="*", unit=UsageUnit.AUDIO_SECONDS,
         price_usd=Decimal("0.0043"), per_units=60, effective_from=_D),
    Rate(provider=Provider.ELEVENLABS, model="*", unit=UsageUnit.CHARACTERS,
         price_usd=Decimal("0.30"), per_units=1_000, effective_from=_D),
]


class SupabaseRateRepository:
    def __init__(self, client: Client):
        self.client = client

    def list(self) -> list[Rate]:
        return [Rate(**r) for r in self.client.table(TABLE).select("*").execute().data]

    def create(self, rate: Rate) -> None:
        self.client.table(TABLE).insert(rate.model_dump(mode="json", exclude_none=True)).execute()


class DemoRateRepository:
    def list(self) -> list[Rate]:
        return list(DEMO_RATES)

    def create(self, rate: Rate) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")
