from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from models.schemas import BudgetAlert

TABLE = "budget_alerts"


class SupabaseAlertRepository:
    def __init__(self, client: Client):
        self.client = client

    def list(self) -> list[BudgetAlert]:
        try:
            rows = self.client.table(TABLE).select("*").execute().data
        except APIError as exc:
            if exc.code == "PGRST205":  # falta migración 007: sin alertas, no romper la app
                return []
            raise
        return [BudgetAlert(**r) for r in rows]

    def save(self, alert: BudgetAlert) -> None:
        row = alert.model_dump(mode="json") | {"updated_at": datetime.now(timezone.utc).isoformat()}
        self.client.table(TABLE).upsert(row, on_conflict="campaign_id").execute()

    def delete(self, campaign_id: UUID) -> None:
        self.client.table(TABLE).delete().eq("campaign_id", str(campaign_id)).execute()


class DemoAlertRepository:
    def list(self) -> list[BudgetAlert]:
        from decimal import Decimal

        from repositories.campaign_repository import DEMO_CAMPAIGNS

        return [BudgetAlert(campaign_id=c.id, limit_amount=Decimal(str(c.monthly_budget_usd)))
                for c in DEMO_CAMPAIGNS if c.monthly_budget_usd]

    def save(self, alert: BudgetAlert) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def delete(self, campaign_id: UUID) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")
