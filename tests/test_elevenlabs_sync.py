from datetime import date
from decimal import Decimal

from integrations.elevenlabs_sync import UNKNOWN, VoiceInfo, build_catalog, build_events
from models.schemas import UsageSource, UsageUnit

D13 = date(2026, 10, 13)


def _by(events):
    return {(e.metadata["agent_name"], e.metadata["component"]): e for e in events}


def test_cost_is_billed_credits_split_call_and_llm():
    minutes = {("CCU Limpio", D13): 1023.0}
    credits = {("CCU Limpio", D13): 2_561_796.0, ("CCU Limpio (LLM)", D13): 7_447_837.0}
    ev = _by(build_events(minutes, credits))
    voice, llm = ev[("CCU Limpio", "voice")], ev[("CCU Limpio", "llm")]
    assert voice.cost_usd == Decimal("263.864988") and llm.cost_usd == Decimal("767.127211")  # × 0.000103
    assert voice.quantities == {UsageUnit.AUDIO_SECONDS: Decimal("61380.0")}
    assert voice.external_id == "resource:2026-10-13:CCU Limpio"
    assert llm.external_id == "resource:2026-10-13:CCU Limpio (LLM)"
    assert voice.metadata["cost_basis"] == "billed_credits" and voice.source == UsageSource.PROVIDER_SYNC


def test_month_matches_invoice_price():
    # Septiembre: 247,855,738 créditos facturados en $25,549.25
    ev = build_events({}, {("Agente", D13): 247_855_738.0})
    assert abs(float(ev[0].cost_usd) - 25_549.25) / 25_549.25 < 0.001


def test_voice_library_surcharge_split_by_minutes_among_library_voices():
    voices = {"R7": VoiceInfo("Gaby", "v1", True), "CCU": VoiceInfo("Antonio", "v2", True),
              "Propia": VoiceInfo("Mi voz", "v3", False)}
    minutes = {("R7", D13): 900.0, ("CCU", D13): 100.0, ("Propia", D13): 500.0}
    credits = {("R7", D13): 1.0, ("CCU", D13): 1.0, ("Propia", D13): 1.0, (UNKNOWN, D13): 100_000.0}
    ev = _by(build_events(minutes, credits, voices))
    assert ("Propia", "voice_library") not in ev  # la voz propia no genera recargo
    assert ev[("R7", "voice_library")].cost_usd == Decimal("9.27")  # 90 % × 100k × 0.000103
    assert ev[("CCU", "voice_library")].cost_usd == Decimal("1.03")
    assert ev[("R7", "voice_library")].metadata["voice_name"] == "Gaby"
    assert ev[("R7", "voice")].metadata["voice_name"] == "Gaby"


def test_surcharge_without_library_agents_stays_unassigned():
    events = build_events({}, {(UNKNOWN, D13): 483_361.0})
    assert len(events) == 1 and events[0].metadata["agent_name"] == UNKNOWN
    assert events[0].cost_usd == Decimal("49.786183")


def test_agent_with_minutes_but_no_llm_credits_has_no_llm_row():
    ev = _by(build_events({("A", D13): 10.0}, {("A", D13): 500.0}))
    assert ("A", "llm") not in ev and ev[("A", "voice")].cost_usd == Decimal("0.0515")


def test_catalog_includes_agents_and_names_seen_in_usage():
    events = build_events({("Agente A", D13): 1.0}, {("Agente A", D13): 10.0, (UNKNOWN, D13): 10.0})
    agents = [{"agent_id": "ag1", "name": "Agente A"}, {"agent_id": "ag2", "name": "Agente A"},
              {"agent_id": "ag3", "name": "Nuevo", "archived": True}]
    catalog = {r.resource_key: r for r in build_catalog(agents, events)}
    assert set(catalog) == {"Agente A", UNKNOWN, "Nuevo"}
    assert catalog["Agente A"].provider_ref == "ag1"  # nombre repetido: primero gana
    assert catalog["Nuevo"].active is False
