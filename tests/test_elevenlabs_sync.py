from datetime import date
from decimal import Decimal

from integrations.elevenlabs_sync import UNKNOWN, AgentRate, VoiceInfo, build_catalog, build_events
from models.schemas import UsageSource, UsageUnit

D13, D14, D20 = date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 20)
CCU_RATE = AgentRate(per_min_total=Decimal("0.0947"), per_min_llm=Decimal("0.0378"), sample_size=292)


def test_cost_is_minutes_times_sampled_rate_split_like_panel():
    events = build_events({("CCU Limpio", D13): 1024.0, ("CCU Limpio (LLM)", D13): 5.0},
                          {("CCU Limpio", D13): CCU_RATE})
    assert len(events) == 2  # la serie "(LLM)" de stats no genera registros propios
    voice, llm = events
    assert voice.cost_usd + llm.cost_usd == Decimal("96.9728")  # ≈ panel $97.40
    assert llm.cost_usd == Decimal("38.7072")  # ≈ panel LLM $38.80
    assert voice.quantities == {UsageUnit.AUDIO_SECONDS: Decimal("61440.0")}
    assert voice.external_id == "resource:2026-10-13:CCU Limpio"
    assert llm.external_id == "resource:2026-10-13:CCU Limpio (LLM)"
    assert voice.metadata["estimated"] and voice.metadata["sample_size"] == 292
    assert voice.source == UsageSource.PROVIDER_SYNC


def test_day_without_sample_uses_nearest_day_rate():
    events = build_events({("CCU Limpio", D14): 100.0}, {("CCU Limpio", D13): CCU_RATE, ("CCU Limpio", D20): CCU_RATE})
    assert events[0].metadata["rate_from_day"] == "2026-10-13"
    assert events[0].cost_usd + events[1].cost_usd == Decimal("9.47")


def test_agent_without_any_rate_is_flagged_with_zero_cost():
    events = build_events({("Agente borrado", D13): 50.0}, {})
    assert all(e.cost_usd == 0 and e.metadata["missing_rate"] for e in events)


def test_voice_library_surcharge_split_by_minutes_among_library_voices():
    voices = {"R7": VoiceInfo("Gaby", "v1", True), "CCU": VoiceInfo("Antonio", "v2", True),
              "Propia": VoiceInfo("Mi voz", "v3", False)}
    minutes = {("R7", D13): 900.0, ("CCU", D13): 100.0, ("Propia", D13): 500.0}
    events = [e for e in build_events(minutes, {}, {D13: 100000.0}, voices) if e.metadata["component"] == "voice_library"]
    by = {e.metadata["agent_name"]: e for e in events}
    assert set(by) == {"R7", "CCU"}  # la voz propia no genera recargo
    assert by["R7"].cost_usd == Decimal("8.964") and by["CCU"].cost_usd == Decimal("0.996")  # 100k créd × 0.0000996
    assert by["R7"].metadata["voice_name"] == "Gaby"
    assert by["R7"].external_id == "resource:2026-10-13:R7 (Voice Library)"


def test_surcharge_without_library_agents_stays_unassigned():
    events = build_events({}, {}, {D13: 483361.0})
    assert len(events) == 1 and events[0].metadata["agent_name"] == UNKNOWN
    assert events[0].cost_usd == Decimal("48.14275560")
    assert events[0].external_id == f"resource:2026-10-13:{UNKNOWN}"


def test_catalog_includes_agents_and_names_seen_in_usage():
    events = build_events({("Agente A", D13): 1.0}, {}, {D13: 10.0})
    agents = [{"agent_id": "ag1", "name": "Agente A"}, {"agent_id": "ag2", "name": "Agente A"},
              {"agent_id": "ag3", "name": "Nuevo", "archived": True}]
    catalog = {r.resource_key: r for r in build_catalog(agents, events)}
    assert set(catalog) == {"Agente A", UNKNOWN, "Nuevo"}
    assert catalog["Agente A"].provider_ref == "ag1"  # nombre repetido: primero gana
    assert catalog["Nuevo"].active is False
