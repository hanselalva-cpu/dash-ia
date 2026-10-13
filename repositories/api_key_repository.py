from uuid import UUID

from supabase import Client

from models.schemas import ApiKey

TABLE = "api_keys"


class SupabaseApiKeyRepository:
    def __init__(self, client: Client):
        self.client = client

    def list(self) -> list[ApiKey]:
        return [ApiKey(**r) for r in self.client.table(TABLE).select("*").order("label").execute().data]

    def get(self, api_key_id: UUID) -> ApiKey | None:
        rows = self.client.table(TABLE).select("*").eq("id", str(api_key_id)).limit(1).execute().data
        return ApiKey(**rows[0]) if rows else None

    def create(self, api_key: ApiKey) -> ApiKey:
        row = api_key.model_dump(mode="json", exclude_none=True)
        return ApiKey(**self.client.table(TABLE).insert(row).execute().data[0])


class DemoApiKeyRepository:
    def list(self) -> list[ApiKey]:
        return []

    def get(self, api_key_id: UUID) -> ApiKey | None:
        return None

    def create(self, api_key: ApiKey) -> ApiKey:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")
