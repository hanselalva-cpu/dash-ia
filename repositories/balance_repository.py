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

    def purchases(self, provider: str | None = None, since: datetime | None = None) -> list[dict]:
        """Recargas por API y pagos manuales. provider=None → todos los proveedores."""
        try:
            q = self.client.table(PURCHASES).select("*")
            if provider:
                q = q.eq("provider", provider)
            if since:
                q = q.gte("created_at", since.isoformat())
            return q.order("created_at").execute().data
        except APIError as exc:
            if exc.code == "PGRST205":
                return []
            raise

    def add_manual_payment(self, provider: str, paid_at: datetime, amount: float, currency: str,
                           amount_usd: float, note: str | None) -> None:
        from uuid import uuid4

        self.client.table(PURCHASES).insert({
            "provider": provider, "order_id": f"manual-{uuid4()}", "created_at": paid_at.isoformat(),
            "amount_usd": round(amount_usd, 4), "order_type": "manual", "source": "manual",
            "currency": currency, "amount_original": amount, "note": note or None,
        }).execute()

    def delete_manual_payment(self, provider: str, order_id: str) -> None:
        """Solo pagos manuales: las recargas por API se vuelven a descargar en cada sincronización."""
        (self.client.table(PURCHASES).delete().eq("provider", provider).eq("order_id", order_id)
         .eq("source", "manual").execute())


class DemoBalanceRepository:
    def insert(self, provider: str, amount_usd: float) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def history(self, provider: str, since: datetime) -> list[dict]:
        return []

    def upsert_purchases(self, provider: str, orders: list[dict]) -> int:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def purchases(self, provider: str | None = None, since: datetime | None = None) -> list[dict]:
        return []

    def add_manual_payment(self, *args, **kwargs) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def delete_manual_payment(self, provider: str, order_id: str) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")
