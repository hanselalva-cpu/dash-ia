from __future__ import annotations

from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

TABLE = "provider_balances"
PURCHASES = "provider_purchases"


class SupabaseBalanceRepository:
    def __init__(self, client: Client):
        self.client = client

    def insert(self, provider: str, amount_usd: float) -> None:
        try:
            self.client.table(TABLE).insert({
                "provider": provider, "amount_usd": amount_usd,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except APIError as exc:
            if exc.code == "PGRST205":  # falta migración 008
                print("AVISO: falta la tabla provider_balances (migración 008); saldo no guardado")
                return
            raise

    def history(self, provider: str, since: datetime) -> list[dict]:
        try:
            return (self.client.table(TABLE).select("captured_at,amount_usd").eq("provider", provider)
                    .gte("captured_at", since.isoformat()).order("captured_at").execute().data)
        except APIError as exc:
            if exc.code == "PGRST205":
                return []
            raise


    def upsert_purchases(self, provider: str, orders: list[dict]) -> int:
        rows = [{"provider": provider, "order_id": o["order_id"], "created_at": o["created"],
                 "amount_usd": float(o.get("amount") or 0), "order_type": o.get("order_type")}
                for o in orders if o.get("order_id") and o.get("created")]
        if not rows:
            return 0
        try:
            return len(self.client.table(PURCHASES).upsert(rows, on_conflict="provider,order_id").execute().data)
        except APIError as exc:
            if exc.code == "PGRST205":  # falta migración 009
                print("AVISO: falta la tabla provider_purchases (migración 009); recargas no guardadas")
                return 0
            raise

    def purchases(self, provider: str, since: datetime | None = None) -> list[dict]:
        try:
            q = self.client.table(PURCHASES).select("order_id,created_at,amount_usd,order_type").eq("provider", provider)
            if since:
                q = q.gte("created_at", since.isoformat())
            return q.order("created_at").execute().data
        except APIError as exc:
            if exc.code == "PGRST205":
                return []
            raise


class DemoBalanceRepository:
    def insert(self, provider: str, amount_usd: float) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def history(self, provider: str, since: datetime) -> list[dict]:
        return []

    def upsert_purchases(self, provider: str, orders: list[dict]) -> int:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def purchases(self, provider: str, since: datetime | None = None) -> list[dict]:
        return []
