from datetime import date
from decimal import Decimal

from integrations.deepgram_sync import build_events
from models.schemas import Provider, Rate, UsageUnit

RESULTS = [
    {"hours": 2.0, "requests": 10,
     "grouping": {"start": "2026-10-10", "end": "2026-10-10", "accessor": "k1", "models": ["uuid-n3"], "method": "sync"}},
    {"hours": 0.0, "requests": 0,
     "grouping": {"start": "2026-10-10", "end": "2026-10-10", "accessor": "k2", "models": ["uuid-n3"], "method": "sync"}},
]
RATE = Rate(provider=Provider.DEEPGRAM, model="*", unit=UsageUnit.AUDIO_SECONDS, price_usd=Decimal("0.0043"),
            per_units=60, effective_from=date(2026, 1, 1))


def test_hours_priced_with_rates():
    events = build_events(RESULTS, {"k1": "Kairoo R7"}, {"uuid-n3": "nova-3-general"}, [RATE])
    assert len(events) == 1  # 0 horas se omite
    e = events[0]
    assert e.model == "nova-3-general"
    assert e.quantities[UsageUnit.AUDIO_SECONDS] == Decimal("7200.000")
    assert e.cost_usd == Decimal("0.516")  # 120 min × 0.0043
    assert e.metadata["key_name"] == "Kairoo R7"
    assert e.external_id == "breakdown:2026-10-10:k1:nova-3-general:sync"


def test_model_versions_with_same_name_are_merged():
    rows = [
        {"hours": 1.0, "requests": 3, "grouping": {"start": "2026-10-10", "accessor": "k1", "models": ["v1"], "method": "sync"}},
        {"hours": 0.5, "requests": 2, "grouping": {"start": "2026-10-10", "accessor": "k1", "models": ["v2"], "method": "sync"}},
    ]
    events = build_events(rows, {}, {"v1": "nova-3-general", "v2": "nova-3-general"}, [RATE])
    assert len(events) == 1
    assert events[0].quantities[UsageUnit.AUDIO_SECONDS] == Decimal("5400.000")
    assert events[0].metadata["requests"] == 5


def test_missing_rate_flagged():
    e = build_events(RESULTS, {}, {}, [])[0]
    assert e.cost_usd == 0 and e.metadata["missing_rates"] == ["audio_seconds"]
    assert e.metadata["key_name"] == "k1" and e.model == "uuid-n3"
