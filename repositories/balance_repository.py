from __future__ import annotations

from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

TABLE = "provider_balances"


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


class DemoBalanceRepository:
    def insert(self, provider: str, amount_usd: float) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def history(self, provider: str, since: datetime) -> list[dict]:
        return []
