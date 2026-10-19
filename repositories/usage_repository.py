from datetime import datetime
from pathlib import Path

from supabase import Client

from models.schemas import UsageEvent

TABLE = "usage_events"
DEMO_CSV = Path(__file__).resolve().parent.parent / "examples" / "usage_demo.csv"


def _to_row(event: UsageEvent) -> dict:
    row = event.model_dump(mode="json", exclude_none=True, exclude={"id"})
    row["quantities"] = {str(k): float(v) for k, v in event.quantities.items()}
    return row


class SupabaseUsageRepository:
    def __init__(self, client: Client):
        self.client = client

    def insert(self, event: UsageEvent) -> UsageEvent:
        return UsageEvent(**self.client.table(TABLE).insert(_to_row(event)).execute().data[0])

    def upsert_many(self, events: list[UsageEvent]) -> int:
        """Idempotente por (provider, external_id): reimportar el mismo CSV no duplica."""
        rows = [_to_row(e) for e in events]
        saved = 0
        for i in range(0, len(rows), 500):
            batch = rows[i:i + 500]
            saved += len(self.client.table(TABLE).upsert(batch, on_conflict="provider,external_id").execute().data)
        return saved

    def delete_provider_sync(self, provider, start: datetime, end: datetime, metadata: dict | None = None) -> None:
        """Borra registros sincronizados de un proveedor en [start, end) antes de reemplazarlos.
        `metadata` limita el borrado a registros con esos valores (ej. {"component": "voice_library"})."""
        q = (self.client.table(TABLE).delete()
             .eq("provider", str(provider)).eq("source", "provider_sync")
             .gte("occurred_at", start.isoformat()).lt("occurred_at", end.isoformat()))
        for key, value in (metadata or {}).items():
            q = q.eq(f"metadata->>{key}", value)
        q.execute()

    def list(self, start: datetime, end: datetime, page_size: int = 1000) -> list[UsageEvent]:
        # PostgREST corta en 1000 filas por respuesta: paginar con range().
        rows, offset = [], 0
        while True:
            page = (
                self.client.table(TABLE)
                .select("*")
                .gte("occurred_at", start.isoformat())
                .lt("occurred_at", end.isoformat())
                .order("occurred_at")
                .order("id")
                .range(offset, offset + page_size - 1)
                .execute()
                .data
            )
            rows += page
            if len(page) < page_size:
                return [UsageEvent(**r) for r in rows]
            offset += page_size


class DemoUsageRepository:
    """Lee examples/usage_demo.csv y calcula costos con DEMO_RATES."""

    def __init__(self):
        from repositories.rate_repository import DEMO_RATES
        from services.import_service import parse_usage_csv
        from services.pricing_service import calculate_cost

        result = parse_usage_csv(DEMO_CSV.read_text(encoding="utf-8"))
        for event in result.events:
            event.cost_usd = calculate_cost(event, DEMO_RATES).total_usd
        self._events = result.events

    def insert(self, event: UsageEvent) -> UsageEvent:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def upsert_many(self, events: list[UsageEvent]) -> int:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def delete_provider_sync(self, provider, start: datetime, end: datetime, metadata: dict | None = None) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def list(self, start: datetime, end: datetime) -> list[UsageEvent]:
        return [e for e in self._events if start <= e.occurred_at < end]
