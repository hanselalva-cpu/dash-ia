from decimal import Decimal

from integrations.openai_sync import NO_KEY, build_events
from models.schemas import Provider, UsageSource

BUCKET = {
    "start_time": 1791158400,  # 2026-10-05 UTC
    "results": [
        {"amount": {"value": 1.25, "currency": "usd"}, "api_key_id": "key_A", "project_id": "proj_1",
         "line_item": "gpt-4o-mini, input"},
        {"amount": {"value": 0.0, "currency": "usd"}, "api_key_id": "key_A", "project_id": "proj_1",
         "line_item": "gpt-4o-mini, output"},
        {"amount": {"value": "0.5", "currency": "usd"}, "api_key_id": None, "project_id": "proj_1",
         "line_item": "web search"},
    ],
}
NAMES = {"key_A": {"name": "R7 Virtual", "project_id": "proj_1", "project_name": "Default project"}}


def test_maps_costs_to_key_names():
    events = build_events([BUCKET], NAMES)
    assert len(events) == 2  # monto 0 se omite
    e = events[0]
    assert e.provider == Provider.OPENAI and e.source == UsageSource.PROVIDER_SYNC
    assert e.cost_usd == Decimal("1.25")
    assert e.metadata["key_name"] == "R7 Virtual"
    assert e.metadata["project_name"] == "Default project"
    assert e.external_id == "cost:2026-10-05:proj_1:key_A:gpt-4o-mini, input"


def test_cost_without_key():
    e = build_events([BUCKET], NAMES)[1]
    assert e.metadata["key_name"] == NO_KEY and e.cost_usd == Decimal("0.5")


def test_daily_records_keep_calendar_date_in_mexico():
    from zoneinfo import ZoneInfo

    e = build_events([BUCKET], NAMES)[0]
    assert e.occurred_at.hour == 12
    assert e.occurred_at.astimezone(ZoneInfo("America/Mexico_City")).date().isoformat() == "2026-10-05"
