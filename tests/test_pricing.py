from datetime import date, datetime, timezone
from decimal import Decimal

from models.schemas import Provider, Rate, UsageEvent, UsageUnit
from services.pricing_service import calculate_cost, find_rate


def rate(model, unit, price, per_units=1_000_000, start=date(2026, 1, 1), end=None, provider=Provider.OPENAI):
    return Rate(provider=provider, model=model, unit=unit, price_usd=Decimal(price), per_units=per_units,
                effective_from=start, effective_to=end)


def event(quantities, model="gpt-4o-mini", when=datetime(2026, 5, 1, tzinfo=timezone.utc), provider=Provider.OPENAI):
    return UsageEvent(provider=provider, model=model, quantities=quantities, occurred_at=when)


def test_cost_per_million_tokens():
    rates = [rate("gpt-4o-mini", UsageUnit.INPUT_TOKENS, "0.15"), rate("gpt-4o-mini", UsageUnit.OUTPUT_TOKENS, "0.60")]
    b = calculate_cost(event({UsageUnit.INPUT_TOKENS: 1_000_000, UsageUnit.OUTPUT_TOKENS: 500_000}), rates)
    assert b.total_usd == Decimal("0.45")
    assert b.complete


def test_exact_model_beats_wildcard():
    rates = [rate("*", UsageUnit.INPUT_TOKENS, "9"), rate("gpt-4o-mini", UsageUnit.INPUT_TOKENS, "1")]
    assert find_rate(rates, Provider.OPENAI, "gpt-4o-mini", UsageUnit.INPUT_TOKENS, date(2026, 5, 1)).price_usd == 1


def test_wildcard_used_when_no_exact():
    rates = [rate("*", UsageUnit.AUDIO_SECONDS, "0.0043", per_units=60, provider=Provider.DEEPGRAM)]
    b = calculate_cost(event({UsageUnit.AUDIO_SECONDS: 120}, model="nova-3", provider=Provider.DEEPGRAM), rates)
    assert b.total_usd == Decimal("0.0086")


def test_rate_versioning_by_date():
    old = rate("gpt-4o-mini", UsageUnit.INPUT_TOKENS, "1", start=date(2026, 1, 1), end=date(2026, 6, 1))
    new = rate("gpt-4o-mini", UsageUnit.INPUT_TOKENS, "2", start=date(2026, 6, 1))
    may = datetime(2026, 5, 31, tzinfo=timezone.utc)
    june = datetime(2026, 6, 1, tzinfo=timezone.utc)
    q = {UsageUnit.INPUT_TOKENS: 1_000_000}
    assert calculate_cost(event(q, when=may), [old, new]).total_usd == 1
    assert calculate_cost(event(q, when=june), [old, new]).total_usd == 2  # effective_to exclusivo


def test_missing_rate_reported_not_raised():
    b = calculate_cost(event({UsageUnit.INPUT_TOKENS: 10, UsageUnit.OUTPUT_TOKENS: 10}),
                       [rate("gpt-4o-mini", UsageUnit.INPUT_TOKENS, "1")])
    assert b.missing_units == [UsageUnit.OUTPUT_TOKENS]
    assert not b.complete


def test_zero_quantity_ignored():
    b = calculate_cost(event({UsageUnit.CACHED_INPUT_TOKENS: 0}), [])
    assert b.complete and b.total_usd == 0


def test_other_provider_rate_not_used():
    rates = [rate("*", UsageUnit.INPUT_TOKENS, "1", provider=Provider.ANTHROPIC)]
    assert find_rate(rates, Provider.OPENAI, "gpt-4o-mini", UsageUnit.INPUT_TOKENS, date(2026, 5, 1)) is None
