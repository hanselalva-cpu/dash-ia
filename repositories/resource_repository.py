from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from models.schemas import ProviderResource

TABLE = "provider_resources"


class SupabaseResourceRepository:
    def __init__(self, client: Client):
        self.client = client

    def list(self) -> list[ProviderResource]:
        try:
            rows = self.client.table(TABLE).select("*").order("provider").order("name").execute().data
        except APIError as exc:
            if exc.code == "PGRST205":  # tabla aún no creada (falta migración 006): sin catálogo, no romper la app
                return []
            raise
        return [ProviderResource(**r) for r in rows]

    def upsert_catalog(self, resources: list[ProviderResource]) -> int:
        """Alta/actualización desde los proveedores. No toca campaign_id (no va en el payload)."""
        if not resources:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            r.model_dump(mode="json", exclude={"id", "campaign_id"}) | {"last_synced_at": now}
            for r in resources
        ]
        try:
            return len(self.client.table(TABLE).upsert(rows, on_conflict="provider,resource_key").execute().data)
        except APIError as exc:
            if exc.code == "PGRST205":
                print("AVISO: falta la tabla provider_resources (migración 006); catálogo no actualizado")
                return 0
            raise

    def assign(self, campaign_id: UUID, resource_ids: set[UUID]) -> None:
        """Deja asignados a la campaña exactamente `resource_ids` (quita los que ya no estén)."""
        current = {
            UUID(r["id"])
            for r in self.client.table(TABLE).select("id").eq("campaign_id", str(campaign_id)).execute().data
        }
        to_remove = current - resource_ids
        if to_remove:
            self.client.table(TABLE).update({"campaign_id": None}).in_("id", [str(i) for i in to_remove]).execute()
        if resource_ids:
            self.client.table(TABLE).update({"campaign_id": str(campaign_id)}).in_(
                "id", [str(i) for i in resource_ids]
            ).execute()


class DemoResourceRepository:
    def list(self) -> list[ProviderResource]:
        return []

    def upsert_catalog(self, resources: list[ProviderResource]) -> int:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def assign(self, campaign_id: UUID, resource_ids: set[UUID]) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")
