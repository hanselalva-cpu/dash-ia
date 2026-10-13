from decimal import Decimal
from uuid import uuid4

from integrations import anthropic_adapter, openai_adapter
from integrations.usage_recorder import UsageRecorder
from models.schemas import ApiKey, Provider, UsageUnit
from repositories.rate_repository import DemoRateRepository
from services.campaign_service import resolve_campaign_id

KEY_CAMPAIGN = uuid4()
KEY = ApiKey(id=uuid4(), provider=Provider.ANTHROPIC, label="prod", key_hint="…abcd", key_hash="h",
             default_campaign_id=KEY_CAMPAIGN)


def test_explicit_campaign_wins():
    explicit = uuid4()
    assert resolve_campaign_id(explicit, KEY) == explicit


def test_falls_back_to_key_default():
    assert resolve_campaign_id(None, KEY) == KEY_CAMPAIGN


def test_unattributed():
    assert resolve_campaign_id(None, None) is None


class MemoryUsageRepo:
    def __init__(self):
        self.saved = []

    def insert(self, event):
        self.saved.append(event)
        return event


class MemoryKeyRepo:
    def get(self, api_key_id):
        return KEY if api_key_id == KEY.id else None


def test_recorder_attributes_and_prices():
    usage = MemoryUsageRepo()
    recorder = UsageRecorder(usage, DemoRateRepository(), MemoryKeyRepo())
    event = recorder.record(Provider.ANTHROPIC, "claude-haiku-5-5",
                            {UsageUnit.INPUT_TOKENS: 1_000_000, UsageUnit.OUTPUT_TOKENS: 100_000}, api_key_id=KEY.id)
    assert event.campaign_id == KEY_CAMPAIGN
    assert event.cost_usd == Decimal("1.5")
    assert usage.saved == [event]


def test_recorder_flags_missing_rate():
    recorder = UsageRecorder(MemoryUsageRepo(), DemoRateRepository())
    event = recorder.record(Provider.OPENAI, "modelo-sin-tarifa", {UsageUnit.INPUT_TOKENS: 10})
    assert event.cost_usd == 0
    assert event.metadata["missing_rates"] == ["input_tokens"]


def test_openai_adapter_splits_cached_tokens():
    resp = {"usage": {"prompt_tokens": 1000, "completion_tokens": 50, "prompt_tokens_details": {"cached_tokens": 600}}}
    q = openai_adapter.quantities_from_response(resp)
    assert q[UsageUnit.INPUT_TOKENS] == 400 and q[UsageUnit.CACHED_INPUT_TOKENS] == 600


def test_anthropic_adapter_reads_cache_fields():
    resp = {"usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100,
                      "cache_creation_input_tokens": 20}}
    q = anthropic_adapter.quantities_from_response(resp)
    assert q == {UsageUnit.INPUT_TOKENS: 10, UsageUnit.CACHED_INPUT_TOKENS: 100,
                 UsageUnit.CACHE_WRITE_TOKENS: 20, UsageUnit.OUTPUT_TOKENS: 5}


# --- Atribución por catálogo de recursos -------------------------------------------------------------------
from datetime import datetime, timezone  # noqa: E402

from models.schemas import ProviderResource, ResourceKind, UsageEvent  # noqa: E402
from services.campaign_service import attribute_campaigns  # noqa: E402

R7 = uuid4()


def _event(provider, **metadata):
    return UsageEvent(provider=provider, model="m", occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
                      metadata=metadata)


def test_resource_catalog_attributes_each_provider():
    resources = [
        ProviderResource(provider=Provider.OPENAI, kind=ResourceKind.API_KEY, resource_key="key_A", name="R7 Virtual",
                         campaign_id=R7),
        ProviderResource(provider=Provider.DEEPGRAM, kind=ResourceKind.API_KEY, resource_key="dg-1", name="Kairoo R7",
                         campaign_id=R7),
        ProviderResource(provider=Provider.ELEVENLABS, kind=ResourceKind.AGENT, resource_key="Agente cobranza",
                         name="Agente cobranza", campaign_id=R7),
        ProviderResource(provider=Provider.OPENAI, kind=ResourceKind.API_KEY, resource_key="key_B", name="libre"),
    ]
    events = attribute_campaigns([
        _event(Provider.OPENAI, openai_api_key_id="key_A"),
        _event(Provider.DEEPGRAM, deepgram_api_key_id="dg-1"),
        _event(Provider.ELEVENLABS, agent_name="Agente cobranza"),
        _event(Provider.OPENAI, openai_api_key_id="key_B"),
        _event(Provider.DEEPGRAM, openai_api_key_id="key_A"),  # campo de otro proveedor: no cruza
    ], resources)
    assert [e.campaign_id for e in events] == [R7, R7, R7, None, None]


def test_explicit_event_campaign_not_overridden():
    other = uuid4()
    resources = [ProviderResource(provider=Provider.OPENAI, kind=ResourceKind.API_KEY, resource_key="key_A",
                                  name="x", campaign_id=R7)]
    event = _event(Provider.OPENAI, openai_api_key_id="key_A")
    event.campaign_id = other
    assert attribute_campaigns([event], resources)[0].campaign_id == other
