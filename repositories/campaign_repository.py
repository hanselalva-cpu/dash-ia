from uuid import UUID

from supabase import Client

from models.schemas import Campaign

TABLE = "campaigns"

DEMO_CAMPAIGNS = [
    Campaign(id=UUID("11111111-1111-1111-1111-111111111111"), name="Cobranza Q4", client="Banco Demo",
             monthly_budget_usd=150),
    Campaign(id=UUID("22222222-2222-2222-2222-222222222222"), name="Soporte Voz", client="Telco Demo",
             monthly_budget_usd=40),
]


class SupabaseCampaignRepository:
    def __init__(self, client: Client):
        self.client = client

    def list(self) -> list[Campaign]:
        rows = self.client.table(TABLE).select("*").order("name").execute().data
        return [Campaign(**r) for r in rows]

    def create(self, campaign: Campaign) -> Campaign:
        row = campaign.model_dump(mode="json", exclude_none=True)
        return Campaign(**self.client.table(TABLE).insert(row).execute().data[0])

    def update(self, campaign_id: UUID, fields: dict) -> None:
        self.client.table(TABLE).update(fields).eq("id", str(campaign_id)).execute()


class DemoCampaignRepository:
    def list(self) -> list[Campaign]:
        return list(DEMO_CAMPAIGNS)

    def create(self, campaign: Campaign) -> Campaign:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")

    def update(self, campaign_id: UUID, fields: dict) -> None:
        raise NotImplementedError("Modo demo: configura Supabase para escribir")
