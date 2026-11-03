"""Costo diario por agente de ElevenLabs = créditos consumidos × precio por crédito de las facturas.

Por qué así:
- ElevenLabs factura por créditos consumidos. Validado con las facturas: agosto 201.9 M créditos → $20,700.00
  y septiembre 247.9 M → $25,549.25, ambas ≈ $0.000103 por crédito.
- `/v1/usage/character-stats` (breakdown `resource`) da créditos y minutos por agente y día. Cada agente
  aparece como "<agente>" (llamada) y "<agente> (LLM)". El panel de agentes de ElevenLabs muestra un costo
  menor que el facturado (p. ej. CCU Limpio 13-oct: panel $97.40, facturable ~$1,000), así que no se usa.
- "Unknown Resource" es el recargo por voces de la Voice Library: se cobra aparte y sin agente, y aquí se
  reparte cada día entre los agentes con voz de biblioteca según sus minutos.

Tres registros por agente y día: llamada ("voice"), LLM ("llm") y recargo de voz ("voice_library").
Idempotente: external_id = "resource:<día>:<agente>", "... (LLM)", "... (Voice Library)".

Uso:  python -m integrations.elevenlabs_sync --days 3 [--since 2026-06-01] [--until 2026-07-01] [--dry-run]
"""

import argparse
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from integrations._common import day_anchor
from models.schemas import Provider, ProviderResource, ResourceKind, UsageEvent, UsageSource, UsageUnit

BASE_URL = "https://api.elevenlabs.io"
LLM_SUFFIX = " (LLM)"
UNKNOWN = "Unknown Resource"
VOICE_LIBRARY_SUFFIX = " (Voice Library)"
Q = Decimal("0.00000001")
# Precio por crédito de las facturas (ago $20,700.00 / 201,882,202 créd; sep $25,549.25 / 247,855,738 créd).
USD_PER_CREDIT = Decimal("0.000103")


@dataclass
class VoiceInfo:
    name: str
    voice_id: str
    library: bool  # voz copiada de la Voice Library → genera recargo


def _get(client: httpx.Client, path: str, params: dict | None = None, retries: int = 6) -> dict:
    for attempt in range(retries):
        try:
            r = client.get(path, params=params)
        except httpx.TransportError:  # timeouts / cortes de red: reintentar
            if attempt == retries - 1:
                raise
            time.sleep(min(2**attempt, 30))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(2**attempt, 30))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def fetch_daily_stats(client: httpx.Client, metric: str, start: datetime, end: datetime) -> dict[tuple[str, date], float]:
    body = _get(client, "/v1/usage/character-stats", {
        "start_unix": int(start.timestamp() * 1000),
        "end_unix": int(end.timestamp() * 1000),
        "breakdown_type": "resource",
        "metric": metric,
        "aggregation_interval": "day",
        "include_workspace_metrics": "true",
    })
    out = {}
    for resource, values in body.get("usage", {}).items():
        for i, day_ms in enumerate(body.get("time", [])):
            v = values[i] if i < len(values) else None
            if v:
                out[(resource, datetime.fromtimestamp(day_ms / 1000, tz=timezone.utc).date())] = float(v)
    return out


def _cost(credits: float) -> Decimal:
    return (Decimal(str(credits)) * USD_PER_CREDIT).quantize(Q)


# --- Registros ------------------------------------------------------------------------------------------------
def build_surcharge_events(minutes: dict[tuple[str, date], float], surcharge_credits: dict[date, float],
                           voices: dict[str, VoiceInfo]) -> list[UsageEvent]:
    """Recargo Voice Library repartido entre los agentes con voz de biblioteca según sus minutos del día.
    Si ese día ningún agente con voz de biblioteca tuvo minutos, queda como "Unknown Resource" sin agente."""
    events = []
    for day, credits in sorted(surcharge_credits.items()):
        if not credits:
            continue
        users = {a: m for (a, d), m in minutes.items() if d == day and m and a in voices and voices[a].library}
        total_min = sum(users.values())
        if not total_min:
            events.append(UsageEvent(
                occurred_at=day_anchor(day), provider=Provider.ELEVENLABS, model="convai_voice_library_surcharge",
                cost_usd=_cost(credits), source=UsageSource.PROVIDER_SYNC,
                external_id=f"resource:{day.isoformat()}:{UNKNOWN}",
                metadata={"agent_name": UNKNOWN, "component": "voice_library", "granularity": "day",
                          "credits": credits, "cost_basis": "billed_credits"},
            ))
            continue
        for agent, mins in sorted(users.items()):
            share = Decimal(str(mins)) / Decimal(str(total_min))
            agent_credits = float(Decimal(str(credits)) * share)
            events.append(UsageEvent(
                occurred_at=day_anchor(day), provider=Provider.ELEVENLABS, model="convai_voice_library_surcharge",
                cost_usd=_cost(agent_credits), source=UsageSource.PROVIDER_SYNC,
                external_id=f"resource:{day.isoformat()}:{agent}{VOICE_LIBRARY_SUFFIX}",
                metadata={"agent_name": agent, "component": "voice_library", "granularity": "day",
                          "voice_name": voices[agent].name, "voice_id": voices[agent].voice_id,
                          "credits": agent_credits, "share": float(share), "cost_basis": "billed_credits"},
            ))
    return events


def build_events(minutes: dict[tuple[str, date], float], credits: dict[tuple[str, date], float],
                 voices: dict[str, VoiceInfo] | None = None) -> list[UsageEvent]:
    """credits/minutes por (serie de character-stats, día). Series: "<agente>", "<agente> (LLM)",
    "Unknown Resource" (recargo de voz)."""
    voices = voices or {}
    agents_days = {(r.removesuffix(LLM_SUFFIX), d) for (r, d), c in credits.items() if c and r != UNKNOWN}
    agents_days |= {(r, d) for (r, d), m in minutes.items() if m and not r.endswith(LLM_SUFFIX) and r != UNKNOWN}
    events = []
    for agent, day in sorted(agents_days):
        mins = minutes.get((agent, day), 0.0)
        meta = {"agent_name": agent, "granularity": "day", "minutes": mins, "cost_basis": "billed_credits"}
        if agent in voices:
            meta |= {"voice_name": voices[agent].name, "voice_library": voices[agent].library}
        for component, series, suffix in (("voice", agent, ""), ("llm", agent + LLM_SUFFIX, LLM_SUFFIX)):
            used = credits.get((series, day), 0.0)
            if not used and component == "llm":
                continue
            events.append(UsageEvent(
                occurred_at=day_anchor(day),
                provider=Provider.ELEVENLABS,
                model="convai_llm" if component == "llm" else "convai_voice",
                quantities={UsageUnit.AUDIO_SECONDS: Decimal(str(mins)) * 60} if component == "voice" and mins else {},
                cost_usd=_cost(used),
                source=UsageSource.PROVIDER_SYNC,
                external_id=f"resource:{day.isoformat()}:{agent}{suffix}",
                metadata=meta | {"component": component, "credits": used},
            ))
    surcharge = {d: c for (r, d), c in credits.items() if r == UNKNOWN}
    return events + build_surcharge_events(minutes, surcharge, voices)


def fetch_agents(client: httpx.Client) -> list[dict]:
    agents, params = [], {"page_size": 100}
    while True:
        page = _get(client, "/v1/convai/agents", params)
        agents += page.get("agents", [])
        if not page.get("has_more") or not page.get("next_cursor"):
            return agents
        params["cursor"] = page["next_cursor"]


def fetch_agent_voices(client: httpx.Client, ids: dict[str, str], names: set[str]) -> dict[str, VoiceInfo]:
    """Voz actual de cada agente (configuración de hoy: no hay historial de voces por API)."""
    voices, cache = {}, {}
    for name in sorted(names):
        if name not in ids:
            continue
        try:
            tts = (_get(client, f"/v1/convai/agents/{ids[name]}").get("conversation_config") or {}).get("tts") or {}
            vid = tts.get("voice_id")
            if not vid:
                continue
            if vid not in cache:
                v = _get(client, f"/v1/voices/{vid}")
                cache[vid] = VoiceInfo(v.get("name") or vid, vid, (v.get("sharing") or {}).get("status") == "copied")
            voices[name] = cache[vid]
        except httpx.HTTPError:
            continue
    return voices


def build_catalog(agents: list[dict], events: list[UsageEvent]) -> list[ProviderResource]:
    """Agentes por nombre (el uso de ElevenLabs solo trae nombre). Incluye nombres vistos en uso que ya no
    existen como agente (borrados, "Unknown Resource"). Nombres repetidos: se conserva el primero."""
    catalog: dict[str, ProviderResource] = {}
    for agent in agents:
        name = agent.get("name") or agent["agent_id"]
        catalog.setdefault(name, ProviderResource(
            provider=Provider.ELEVENLABS, kind=ResourceKind.AGENT, resource_key=name, name=name,
            provider_ref=agent["agent_id"], active=not agent.get("archived", False)))
    for event in events:
        name = event.metadata.get("agent_name")
        if name and name not in catalog:
            catalog[name] = ProviderResource(provider=Provider.ELEVENLABS, kind=ResourceKind.AGENT,
                                             resource_key=name, name=name, active=False)
    return list(catalog.values())


def fetch_events(api_key: str, start: datetime, end: datetime) -> tuple[list[UsageEvent], list[ProviderResource]]:
    with httpx.Client(base_url=BASE_URL, headers={"xi-api-key": api_key}, timeout=60) as client:
        minutes = fetch_daily_stats(client, "minutes_used", start, end)
        credits = fetch_daily_stats(client, "credits", start, end)
        agents = fetch_agents(client)
        ids = {}
        for a in agents:
            ids.setdefault(a.get("name"), a["agent_id"])
        voices = fetch_agent_voices(client, ids, {r for (r, _), m in minutes.items() if m})
    events = build_events(minutes, credits, voices)
    return events, build_catalog(agents, events)


def main() -> None:
    from collections import Counter

    from config.settings import get_settings
    from repositories import get_repositories

    parser = argparse.ArgumentParser(description="Sincroniza costo diario facturable por agente de ElevenLabs")
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--since", type=date.fromisoformat, help="fecha inicial YYYY-MM-DD (ignora --days)")
    parser.add_argument("--until", type=date.fromisoformat, help="fecha final exclusiva YYYY-MM-DD (default: ahora)")
    parser.add_argument("--dry-run", action="store_true", help="descarga y resume, no guarda en Supabase")
    args = parser.parse_args()

    api_key = get_settings().elevenlabs_api_key.get_secret_value()
    if not api_key:
        raise SystemExit("Falta ELEVENLABS_API_KEY en .env")
    end = (datetime.combine(args.until, datetime.min.time(), tzinfo=timezone.utc) if args.until
           else datetime.now(timezone.utc))
    start = (datetime.combine(args.since, datetime.min.time(), tzinfo=timezone.utc) if args.since
             else datetime.combine((end - timedelta(days=args.days)).date(), datetime.min.time(), tzinfo=timezone.utc))

    events, catalog = fetch_events(api_key, start, end)
    saved = 0
    if not args.dry_run:
        repos = get_repositories()
        repos.resources.upsert_catalog(catalog)
        # Reemplaza el rango completo (incluidos registros de métodos anteriores).
        repos.usage.delete_provider_sync(Provider.ELEVENLABS, start, end)
        saved = repos.usage.upsert_many(events)
    print(f"Catálogo: {len(catalog)} agentes")

    total = Counter()
    for e in events:
        total[f"{e.metadata['agent_name']} [{e.metadata['component']}]"] += float(e.cost_usd)
    print(f"{len(events)} registros día×agente · guardados {saved}{' (dry-run)' if args.dry_run else ''}")
    for name, usd in total.most_common():
        print(f"  {usd:>12,.2f} USD  {name}")


if __name__ == "__main__":
    main()
