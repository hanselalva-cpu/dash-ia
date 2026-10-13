from decimal import Decimal

from integrations.elevenlabs_sync import build_events
from models.schemas import UsageSource, UsageUnit

DAY1, DAY2 = 1791158400000, 1791244800000  # 2026-10-05, 2026-10-06 UTC


def test_builds_one_event_per_agent_day_and_component():
    events = build_events(
        [DAY1, DAY2],
        fiat={"Agente A": [250.0, 0.0], "Agente A (LLM)": [10.0, 5.0]},
        credits={"Agente A": [25000.0, 0.0], "Agente A (LLM)": [1000.0, 500.0]},
        minutes={"Agente A": [3.0, None]},
    )
    assert len(events) == 3  # día 2 de voz sin costo ni créditos se omite
    voice = events[0]
    assert voice.cost_usd == Decimal("2.5")
    assert voice.metadata["agent_name"] == "Agente A" and voice.metadata["component"] == "voice"
    assert voice.quantities == {UsageUnit.AUDIO_SECONDS: Decimal("180")}
    assert voice.source == UsageSource.PROVIDER_SYNC
    assert voice.external_id == "resource:2026-10-05:Agente A"
    llm = [e for e in events if e.metadata["component"] == "llm"]
    assert {e.metadata["agent_name"] for e in llm} == {"Agente A"}
    assert all(e.model == "convai_llm" for e in llm)


def test_none_values_tolerated():
    events = build_events([DAY1], fiat={"X": [None]}, credits={"X": [None]}, minutes={})
    assert events == []


def test_catalog_includes_agents_and_names_seen_in_usage():
    from integrations.elevenlabs_sync import build_catalog

    events = build_events([DAY1], fiat={"Agente A": [1.0], "Unknown Resource": [2.0]},
                          credits={}, minutes={})
    agents = [{"agent_id": "ag1", "name": "Agente A"}, {"agent_id": "ag2", "name": "Agente A"},
              {"agent_id": "ag3", "name": "Nuevo", "archived": True}]
    catalog = {r.resource_key: r for r in build_catalog(agents, events)}
    assert set(catalog) == {"Agente A", "Unknown Resource", "Nuevo"}
    assert catalog["Agente A"].provider_ref == "ag1"  # nombre repetido: primero gana
    assert catalog["Nuevo"].active is False
    assert catalog["Unknown Resource"].provider_ref is None
