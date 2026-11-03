from dataclasses import dataclass
from typing import Any

from config.settings import get_settings


@dataclass
class Repositories:
    campaigns: Any
    api_keys: Any
    rates: Any
    usage: Any
    resources: Any
    alerts: Any
    balances: Any
    demo: bool


def get_repositories() -> Repositories:
    """DEMO_MODE=true → repositorios demo de solo lectura; si no, Supabase (credenciales obligatorias)."""
    settings = get_settings()
    if not settings.demo_mode:
        if not settings.supabase_configured:
            raise RuntimeError("DEMO_MODE=false pero faltan SUPABASE_URL y SUPABASE_PUBLISHABLE_KEY/SECRET_KEY en .env")
        from repositories.alert_repository import SupabaseAlertRepository
        from repositories.balance_repository import SupabaseBalanceRepository
        from repositories.api_key_repository import SupabaseApiKeyRepository
        from repositories.campaign_repository import SupabaseCampaignRepository
        from repositories.rate_repository import SupabaseRateRepository
        from repositories.resource_repository import SupabaseResourceRepository
        from repositories.supabase_client import get_client
        from repositories.usage_repository import SupabaseUsageRepository

        client = get_client()
        return Repositories(
            SupabaseCampaignRepository(client),
            SupabaseApiKeyRepository(client),
            SupabaseRateRepository(client),
            SupabaseUsageRepository(client),
            SupabaseResourceRepository(client),
            SupabaseAlertRepository(client),
            SupabaseBalanceRepository(client),
            demo=False,
        )

    from repositories.alert_repository import DemoAlertRepository
    from repositories.balance_repository import DemoBalanceRepository
    from repositories.api_key_repository import DemoApiKeyRepository
    from repositories.campaign_repository import DemoCampaignRepository
    from repositories.rate_repository import DemoRateRepository
    from repositories.resource_repository import DemoResourceRepository
    from repositories.usage_repository import DemoUsageRepository

    return Repositories(
        DemoCampaignRepository(), DemoApiKeyRepository(), DemoRateRepository(), DemoUsageRepository(),
        DemoResourceRepository(), DemoAlertRepository(), DemoBalanceRepository(), demo=True,
    )
