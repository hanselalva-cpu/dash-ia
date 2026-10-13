"""Descarga el costo diario por agente de ElevenLabs desde /v1/usage/character-stats (breakdown por `resource`).

Tres llamadas por sincronización (créditos, dinero, minutos), sin importar cuántas conversaciones haya.
Cada serie de `resource` es un agente; las que terminan en " (LLM)" son el costo del LLM de ese agente.
Idempotente: external_id = "resource:<día>:<serie>", re-sincronizar actualiza el día en curso.

Uso:  python -m integrations.elevenlabs_sync --days 7 [--dry-run]
"""

import argparse
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from integrations._common import day_anchor
from models.schemas import Provider, ProviderResource, ResourceKind, UsageEvent, UsageSource, UsageUnit

BASE_URL = "https://api.elevenlabs.io"
LLM_SUFFIX = " (LLM)"
# `fiat_units_spent` parece venir en centavos de USD (≈ créditos / 100 en esta cuenta).
# PENDIENTE VALIDAR contra el panel de uso de ElevenLabs; si no cuadra, ajustar aquí.
FIAT_UNITS_PER_USD = Decimal(100)


def _get(client: httpx.Client, path: str, params: dict, retries: int = 5) -> dict:
    for attempt in range(retries):
        r = client.get(path, params=params)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(2**attempt, 30))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def fetch_metric(client: httpx.Client, metric: str, start: datetime, end: datetime) -> tuple[list[int], dict]:
    body = _get(client, "/v1/usage/character-stats", {
        "start_unix": int(start.timestamp() * 1000),
        "end_unix": int(end.timestamp() * 1000),
        "breakdown_type": "resource",
        "metric": metric,
        "aggregation_interval": "day",
        "include_workspace_metrics": "true",
    })
    return body.get("time", []), body.get("usage", {})


def build_events(times: list[int], fiat: dict, credits: dict, minutes: dict) -> list[UsageEvent]:
    events = []
    for resource, values in fiat.items():
        is_llm = resource.endswith(LLM_SUFFIX)
        agent = resource.removesuffix(LLM_SUFFIX)
        for i, day_ms in enumerate(times):
            amount = values[i] if i < len(values) else None
            cred = (credits.get(resource) or [None] * len(times))[i]
            if not amount and not cred:
                continue
            day = datetime.fromtimestamp(day_ms / 1000, tz=timezone.utc)
            mins = (minutes.get(resource) or [None] * len(times))[i]
            events.append(UsageEvent(
                occurred_at=day_anchor(day),
                provider=Provider.ELEVENLABS,
                model="convai_llm" if is_llm else "convai_voice",
                quantities={UsageUnit.AUDIO_SECONDS: Decimal(str(mins or 0)) * 60} if mins else {},
                cost_usd=(Decimal(str(amount or 0)) / FIAT_UNITS_PER_USD).quantize(Decimal("0.00000001")),
                source=UsageSource.PROVIDER_SYNC,
                external_id=f"resource:{day.date().isoformat()}:{resource}",
                metadata={"agent_name": agent, "component": "llm" if is_llm else "voice",
                          "credits": cred, "fiat_units": amount, "granularity": "day"},
            ))
    return events


def fetch_agents(client: httpx.Client) -> list[dict]:
    agents, params = [], {"page_size": 100}
    while True:
        page = _get(client, "/v1/convai/agents", params)
        agents += page.get("agents", [])
        if not page.get("has_more") or not page.get("next_cursor"):
            return agents
        params["cursor"] = page["next_cursor"]


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
        times, fiat = fetch_metric(client, "fiat_units_spent", start, end)
        _, credits = fetch_metric(client, "credits", start, end)
        _, minutes = fetch_metric(client, "minutes_used", start, end)
        agents = fetch_agents(client)
    events = build_events(times, fiat, credits, minutes)
    return events, build_catalog(agents, events)


def main() -> None:
    from collections import Counter

    from config.settings import get_settings
    from repositories import get_repositories

    parser = argparse.ArgumentParser(description="Sincroniza costo diario por agente de ElevenLabs")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--since", type=date.fromisoformat, help="fecha inicial YYYY-MM-DD (ignora --days)")
    parser.add_argument("--dry-run", action="store_true", help="descarga y resume, no guarda en Supabase")
    args = parser.parse_args()

    api_key = get_settings().elevenlabs_api_key.get_secret_value()
    if not api_key:
        raise SystemExit("Falta ELEVENLABS_API_KEY en .env")
    end = datetime.now(timezone.utc)
    start = (datetime.combine(args.since, datetime.min.time(), tzinfo=timezone.utc) if args.since
             else end - timedelta(days=args.days))

    events, catalog = fetch_events(api_key, start, end)
    saved = 0
    if not args.dry_run:
        repos = get_repositories()
        repos.resources.upsert_catalog(catalog)
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
