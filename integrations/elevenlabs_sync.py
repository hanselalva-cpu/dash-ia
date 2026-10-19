"""Costo diario por agente de ElevenLabs = minutos del día × costo por minuto medido en una muestra.

Por qué así:
- El panel de ElevenLabs calcula el costo sumando `metadata.cost_fiat` de cada conversación. Con ~70,000
  conversaciones diarias no es viable pedir el detalle de todas.
- `/v1/usage/character-stats` (breakdown `resource`) da los MINUTOS por agente de forma confiable, pero sus
  créditos/dinero por agente vienen inflados (~4-19× vs. el panel), así que no se usan como costo.
- Costo por minuto = Σ cost_fiat / Σ minutos de una muestra aleatoria de conversaciones del agente y día
  (validado: CCU Limpio 13-oct estimado $96.90 / LLM $38.71 vs. panel $97.40 / $38.80).

Se guardan dos registros por agente y día, como en el panel: total sin LLM ("voice") y LLM ("llm").
"Unknown Resource" (recargo Voice Library) no tiene minutos ni conversaciones: se guarda con costo 0 y sus
créditos en metadata hasta validarlo contra una factura.
Idempotente: external_id = "resource:<día>:<agente>" / "resource:<día>:<agente> (LLM)".

Uso:  python -m integrations.elevenlabs_sync --days 3 [--since 2026-06-18] [--dry-run] [--sample 100]
"""

import argparse
import random
import sys
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
SAMPLE_WINDOWS = 8  # ventanas del día de donde se toman conversaciones, para no sesgar a una sola hora
Q = Decimal("0.00000001")
# Conversaciones previas a ~julio-2026 no traen metadata.cost_fiat, solo créditos (metadata.cost).
# Equivalencia medida en conversaciones que traen ambos: 0.09227/926, 0.0127/128, 0.0185/186 ≈ 99.6 µUSD.
USD_PER_CREDIT = Decimal("0.0000996")


@dataclass
class AgentRate:
    """Costo por minuto medido en una muestra (USD)."""

    per_min_total: Decimal
    per_min_llm: Decimal
    sample_size: int


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


# --- Minutos por agente (confiable) ---------------------------------------------------------------------------
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


# --- Costo por minuto (muestra de conversaciones) -------------------------------------------------------------
def sample_conversations(client: httpx.Client, agent_id: str, day: date, per_window: int = 30) -> list[dict]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    step = timedelta(days=1) / SAMPLE_WINDOWS
    found = {}
    for w in range(SAMPLE_WINDOWS):
        a, b = start + step * w, start + step * (w + 1)
        page = _get(client, "/v1/convai/conversations", {
            "agent_id": agent_id, "page_size": per_window,
            "call_start_after_unix": int(a.timestamp()), "call_start_before_unix": int(b.timestamp()),
        })
        for c in page.get("conversations", []):
            if c.get("status") == "done" and (c.get("call_duration_secs") or 0) > 0:
                found[c["conversation_id"]] = c
    return list(found.values())


def measure_rate(client: httpx.Client, summaries: list[dict], max_n: int, rng: random.Random) -> AgentRate | None:
    picked = rng.sample(summaries, min(max_n, len(summaries)))
    cost = llm = secs = Decimal(0)
    n = 0
    for s in picked:
        try:
            meta = _get(client, f"/v1/convai/conversations/{s['conversation_id']}").get("metadata") or {}
        except httpx.HTTPError:
            continue
        if meta.get("cost_fiat") is not None:
            conv_cost = Decimal(str(meta["cost_fiat"]))
        elif meta.get("cost") is not None:
            conv_cost = Decimal(str(meta["cost"])) * USD_PER_CREDIT  # conversaciones antiguas sin cost_fiat
        else:
            continue
        charging = meta.get("charging") or {}
        cost += conv_cost
        llm += Decimal(str(charging.get("llm_price") or 0))
        secs += Decimal(str(s["call_duration_secs"]))
        n += 1
        time.sleep(0.05)
    if not n or not secs:
        return None
    minutes = secs / 60
    return AgentRate(cost / minutes, llm / minutes, n)


def nearest_rate(rates: dict[tuple[str, date], AgentRate], agent: str, day: date) -> tuple[AgentRate, date] | None:
    own = [(d, r) for (a, d), r in rates.items() if a == agent]
    if not own:
        return None
    d, r = min(own, key=lambda dr: abs((dr[0] - day).days))
    return r, d


# --- Registros ------------------------------------------------------------------------------------------------
@dataclass
class VoiceInfo:
    name: str
    voice_id: str
    library: bool  # voz copiada de la Voice Library → genera recargo


def build_surcharge_events(minutes: dict[tuple[str, date], float], surcharge_credits: dict[date, float],
                           voices: dict[str, VoiceInfo]) -> list[UsageEvent]:
    """Recargo Voice Library: ElevenLabs lo cobra aparte ("Unknown Resource"), no dentro del costo de cada
    conversación. Se reparte cada día entre los agentes con voz de biblioteca según sus minutos.
    Si ese día ningún agente con voz de biblioteca tuvo minutos, queda como "Unknown Resource" sin agente."""
    events = []
    for day, credits in sorted(surcharge_credits.items()):
        if not credits:
            continue
        usd = Decimal(str(credits)) * USD_PER_CREDIT
        users = {a: m for (a, d), m in minutes.items()
                 if d == day and m and a in voices and voices[a].library}
        total_min = sum(users.values())
        if not total_min:
            events.append(UsageEvent(
                occurred_at=day_anchor(day), provider=Provider.ELEVENLABS, model="convai_voice_library_surcharge",
                cost_usd=usd.quantize(Q), source=UsageSource.PROVIDER_SYNC,
                external_id=f"resource:{day.isoformat()}:{UNKNOWN}",
                metadata={"agent_name": UNKNOWN, "component": "voice_library", "granularity": "day",
                          "credits": credits, "estimated": True},
            ))
            continue
        for agent, mins in sorted(users.items()):
            share = Decimal(str(mins)) / Decimal(str(total_min))
            events.append(UsageEvent(
                occurred_at=day_anchor(day), provider=Provider.ELEVENLABS, model="convai_voice_library_surcharge",
                cost_usd=(usd * share).quantize(Q), source=UsageSource.PROVIDER_SYNC,
                external_id=f"resource:{day.isoformat()}:{agent}{VOICE_LIBRARY_SUFFIX}",
                metadata={"agent_name": agent, "component": "voice_library", "granularity": "day",
                          "voice_name": voices[agent].name, "voice_id": voices[agent].voice_id,
                          "credits": float(Decimal(str(credits)) * share), "share": float(share), "estimated": True},
            ))
    return events


def build_events(minutes: dict[tuple[str, date], float], rates: dict[tuple[str, date], AgentRate],
                 surcharge_credits: dict[date, float] | None = None,
                 voices: dict[str, VoiceInfo] | None = None) -> list[UsageEvent]:
    voices = voices or {}
    events = []
    for (agent, day), mins in sorted(minutes.items()):
        if agent.endswith(LLM_SUFFIX) or agent == UNKNOWN or not mins:
            continue
        found = (rates[(agent, day)], day) if (agent, day) in rates else nearest_rate(rates, agent, day)
        meta = {"agent_name": agent, "granularity": "day", "estimated": True, "minutes": mins}
        if agent in voices:
            meta |= {"voice_name": voices[agent].name, "voice_library": voices[agent].library}
        if found:
            rate, rate_day = found
            total = (rate.per_min_total * Decimal(str(mins))).quantize(Q)
            llm = (rate.per_min_llm * Decimal(str(mins))).quantize(Q)
            meta |= {"usd_per_min": float(rate.per_min_total), "llm_usd_per_min": float(rate.per_min_llm),
                     "sample_size": rate.sample_size, "rate_from_day": rate_day.isoformat()}
        else:
            total = llm = Decimal(0)
            meta |= {"missing_rate": True}
        seconds = Decimal(str(mins)) * 60
        for component, cost, suffix in (("voice", total - llm, ""), ("llm", llm, LLM_SUFFIX)):
            events.append(UsageEvent(
                occurred_at=day_anchor(day),
                provider=Provider.ELEVENLABS,
                model="convai_llm" if component == "llm" else "convai_voice",
                quantities={UsageUnit.AUDIO_SECONDS: seconds} if component == "voice" else {},
                cost_usd=cost,
                source=UsageSource.PROVIDER_SYNC,
                external_id=f"resource:{day.isoformat()}:{agent}{suffix}",
                metadata=meta | {"component": component},
            ))
    return events + build_surcharge_events(minutes, surcharge_credits or {}, voices)


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


def fetch_events(api_key: str, start: datetime, end: datetime, sample: int = 100,
                 log=lambda msg: print(msg, file=sys.stderr, flush=True)) -> tuple[list[UsageEvent], list[ProviderResource]]:
    rng = random.Random(42)
    with httpx.Client(base_url=BASE_URL, headers={"xi-api-key": api_key}, timeout=60) as client:
        minutes = fetch_daily_stats(client, "minutes_used", start, end)
        credits = fetch_daily_stats(client, "credits", start, end)
        agents = fetch_agents(client)
        ids = {}
        for a in agents:
            ids.setdefault(a.get("name"), a["agent_id"])
        todo = sorted((a, d) for (a, d), m in minutes.items()
                      if m and not a.endswith(LLM_SUFFIX) and a != UNKNOWN and a in ids)
        rates: dict[tuple[str, date], AgentRate] = {}
        t0 = time.time()
        for i, (agent, day) in enumerate(todo, 1):
            try:
                rate = measure_rate(client, sample_conversations(client, ids[agent], day), sample, rng)
            except httpx.HTTPError as exc:  # un día-agente fallido no tumba la corrida: usa el día más cercano
                log(f"[{i}/{len(todo)}] {day} {agent}: error {type(exc).__name__}, se usará el día más cercano")
                continue
            if rate:
                rates[(agent, day)] = rate
            log(f"[{i}/{len(todo)}] {day} {agent}: "
                + (f"${rate.per_min_total:.4f}/min (n={rate.sample_size})" if rate else "sin muestra")
                + f" · {time.time() - t0:.0f}s")
        voices = fetch_agent_voices(client, ids, {a for (a, _), m in minutes.items() if m})
    surcharge = {d: c for (a, d), c in credits.items() if a == UNKNOWN}
    events = build_events(minutes, rates, surcharge, voices)
    return events, build_catalog(agents, events)


def fetch_surcharge_events(api_key: str, start: datetime, end: datetime) -> list[UsageEvent]:
    """Solo el recargo Voice Library (sin muestrear conversaciones): minutos + créditos + voces."""
    with httpx.Client(base_url=BASE_URL, headers={"xi-api-key": api_key}, timeout=60) as client:
        minutes = fetch_daily_stats(client, "minutes_used", start, end)
        credits = fetch_daily_stats(client, "credits", start, end)
        ids = {}
        for a in fetch_agents(client):
            ids.setdefault(a.get("name"), a["agent_id"])
        voices = fetch_agent_voices(client, ids, {a for (a, _), m in minutes.items() if m})
    return build_surcharge_events(minutes, {d: c for (a, d), c in credits.items() if a == UNKNOWN}, voices)


def main() -> None:
    from collections import Counter

    from config.settings import get_settings
    from repositories import get_repositories

    parser = argparse.ArgumentParser(description="Sincroniza costo diario por agente de ElevenLabs (estimado)")
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--since", type=date.fromisoformat, help="fecha inicial YYYY-MM-DD (ignora --days)")
    parser.add_argument("--until", type=date.fromisoformat, help="fecha final exclusiva YYYY-MM-DD (default: ahora)")
    parser.add_argument("--sample", type=int, default=100, help="conversaciones a medir por agente y día")
    parser.add_argument("--dry-run", action="store_true", help="descarga y resume, no guarda en Supabase")
    parser.add_argument("--only-surcharge", action="store_true",
                        help="recalcula solo el recargo Voice Library (rápido, no muestrea conversaciones)")
    args = parser.parse_args()

    api_key = get_settings().elevenlabs_api_key.get_secret_value()
    if not api_key:
        raise SystemExit("Falta ELEVENLABS_API_KEY en .env")
    end = (datetime.combine(args.until, datetime.min.time(), tzinfo=timezone.utc) if args.until
           else datetime.now(timezone.utc))
    start = (datetime.combine(args.since, datetime.min.time(), tzinfo=timezone.utc) if args.since
             else datetime.combine((end - timedelta(days=args.days)).date(), datetime.min.time(), tzinfo=timezone.utc))

    if args.only_surcharge:
        events = fetch_surcharge_events(api_key, start, end)
        saved = 0
        if not args.dry_run:
            repos = get_repositories()
            repos.usage.delete_provider_sync(Provider.ELEVENLABS, start, end, {"agent_name": UNKNOWN})
            repos.usage.delete_provider_sync(Provider.ELEVENLABS, start, end, {"component": "voice_library"})
            saved = repos.usage.upsert_many(events)
        by = Counter()
        for e in events:
            by[f"{e.metadata['agent_name']} · {e.metadata.get('voice_name', '—')}"] += float(e.cost_usd)
        dry = " (dry-run)" if args.dry_run else ""
        print(f"Recargo Voice Library: {len(events)} registros · guardados {saved}{dry}")
        for name, usd in by.most_common():
            print(f"  {usd:>12,.2f} USD  {name}")
        return

    events, catalog = fetch_events(api_key, start, end, args.sample)
    saved = 0
    if not args.dry_run:
        repos = get_repositories()
        repos.resources.upsert_catalog(catalog)
        # Reemplaza el rango completo: borra registros previos de ElevenLabs (incluidos los del método anterior)
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
