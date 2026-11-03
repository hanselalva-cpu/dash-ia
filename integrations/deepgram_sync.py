"""Horas de audio por API key y modelo de Deepgram, con el costo real que cobra Deepgram.

Fuentes:
- Horas: /v1/projects/{id}/usage/breakdown agrupado por accessor (API key) + models + method, por día (exacto).
- Costo: cada petición de /requests trae `response.details.usd`. Por key y día se mide $/hora con una muestra
  de peticiones (Σ usd / Σ duración) y se multiplica por las horas del día. La tarifa real varía por key
  (funciones como diarización/NER): validado 11-oct→2-nov, Kairoo R7 $0.390/h, R3 $0.260/h, Provident
  $0.390/h, Pruebas GIo $0.326/h. Si un día no tiene muestra se usa el día más cercano de la misma key, y si
  la key no tiene ninguna, la tarifa de la tabla `rates`.
Idempotente: external_id = "breakdown:<día>:<api_key_id>:<modelo>:<method>".

Uso:  python -m integrations.deepgram_sync --days 30 [--since 2026-06-01] [--dry-run]
"""

import argparse
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from integrations._common import day_anchor
from models.schemas import Provider, ProviderResource, Rate, ResourceKind, UsageEvent, UsageSource, UsageUnit
from services.pricing_service import calculate_cost

BASE_URL = "https://api.deepgram.com"


def _get(client: httpx.Client, path: str, params, retries: int = 5) -> dict:
    for attempt in range(retries):
        r = client.get(path, params=params)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(2**attempt, 30))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def fetch_lookups(client: httpx.Client, project_id: str) -> tuple[dict[str, str], dict[str, str]]:
    """(api_key_id → nombre, model_uuid → nombre canónico)."""
    keys = _get(client, f"/v1/projects/{project_id}/keys", {})
    key_names = {k["api_key"]["api_key_id"]: k["api_key"].get("comment") for k in keys.get("api_keys", [])}
    models = _get(client, "/v1/models", {"include_outdated": "true"})
    model_names = {m["uuid"]: m.get("canonical_name") or m.get("name") for m in models.get("stt", [])}
    return key_names, model_names


def build_events(results: list[dict], key_names: dict[str, str], model_names: dict[str, str],
                 rates: list[Rate]) -> list[UsageEvent]:
    # Varias versiones (UUID) del mismo modelo comparten nombre: se suman en un solo registro.
    merged: dict[str, UsageEvent] = {}
    for row in results:
        seconds = Decimal(str(row.get("hours") or 0)) * 3600
        if not seconds:
            continue
        g = row["grouping"]
        model_ids = g.get("models") or []
        model = ",".join(sorted({model_names.get(m, m) for m in model_ids})) or "unknown"
        accessor = g.get("accessor")
        external_id = f"breakdown:{g['start']}:{accessor}:{model}:{g.get('method')}"
        if external_id in merged:
            prev = merged[external_id]
            prev.quantities[UsageUnit.AUDIO_SECONDS] += seconds
            prev.metadata["requests"] = (prev.metadata.get("requests") or 0) + (row.get("requests") or 0)
            continue
        merged[external_id] = UsageEvent(
            occurred_at=day_anchor(date.fromisoformat(g["start"])),
            provider=Provider.DEEPGRAM,
            model=model,
            quantities={UsageUnit.AUDIO_SECONDS: seconds},
            source=UsageSource.PROVIDER_SYNC,
            external_id=external_id,
            metadata={
                "deepgram_api_key_id": accessor,
                "key_name": key_names.get(accessor) or accessor,
                "method": g.get("method"),
                "requests": row.get("requests"),
                "granularity": "day",
            },
        )

    events = []
    for event in merged.values():
        event.quantities[UsageUnit.AUDIO_SECONDS] = event.quantities[UsageUnit.AUDIO_SECONDS].quantize(Decimal("0.001"))
        breakdown = calculate_cost(event, rates)
        event.cost_usd = breakdown.total_usd
        if not breakdown.complete:
            event.metadata["missing_rates"] = [str(u) for u in breakdown.missing_units]
        events.append(event)
    return events


REQUEST_PAGES = 4  # páginas de 100 peticiones por key y día para medir $/hora


def measure_usd_per_hour(client: httpx.Client, project_id: str, key_id: str, day: date) -> Decimal | None:
    """$/hora real de una key en un día: Σ usd / Σ duración de sus peticiones (las en curso no traen detalle)."""
    usd = secs = Decimal(0)
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    for page in range(REQUEST_PAGES):
        body = _get(client, f"/v1/projects/{project_id}/requests", {
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": (start + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit": 100, "page": page, "accessor": key_id,
        })
        items = body.get("requests", [])
        for item in items:
            if item.get("api_key_id") != key_id:
                continue
            details = (item.get("response") or {}).get("details") or {}
            if details.get("usd") is not None and details.get("duration"):
                usd += Decimal(str(details["usd"]))
                secs += Decimal(str(details["duration"]))
        if len(items) < 100:
            break
    return usd / secs * 3600 if secs else None


def apply_measured_rates(events: list[UsageEvent], measured: dict[tuple[str, date], Decimal]) -> list[UsageEvent]:
    """Reemplaza el costo de tabla por horas × $/hora medido (mismo día, o el más cercano de la misma key)."""
    for event in events:
        key_id, day = event.metadata.get("deepgram_api_key_id"), event.occurred_at.date()
        own = [(d, r) for (k, d), r in measured.items() if k == key_id]
        if not own:
            event.metadata["cost_source"] = "rates_table"
            continue
        rate_day, per_hour = min(own, key=lambda dr: abs((dr[0] - day).days))
        hours = event.quantities[UsageUnit.AUDIO_SECONDS] / 3600
        event.cost_usd = (per_hour * hours).quantize(Decimal("0.00000001"))
        event.metadata.pop("missing_rates", None)
        event.metadata |= {"cost_source": "requests_usd", "usd_per_hour": float(per_hour),
                           "rate_from_day": rate_day.isoformat()}
    return events


def fetch_balance(client: httpx.Client, project_id: str) -> float:
    return sum(float(b.get("amount") or 0) for b in _get(client, f"/v1/projects/{project_id}/balances", {})
               .get("balances", []) if (b.get("units") or "usd") == "usd")


def fetch_events(api_key: str, start: date, end: date, rates: list[Rate],
                 log=print) -> tuple[list[UsageEvent], list[ProviderResource], float]:
    with httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Token {api_key}"}, timeout=120) as client:
        projects = _get(client, "/v1/projects", {}).get("projects", [])
        events = []
        catalog = []
        balance = 0.0
        for project in projects:
            pid = project["project_id"]
            key_names, model_names = fetch_lookups(client, pid)
            body = _get(client, f"/v1/projects/{pid}/usage/breakdown", [
                ("start", start.isoformat()), ("end", end.isoformat()),
                ("grouping", "accessor"), ("grouping", "models"), ("grouping", "method"),
            ])
            project_events = build_events(body.get("results", []), key_names, model_names, rates)
            todo = sorted({(e.metadata["deepgram_api_key_id"], e.occurred_at.date()) for e in project_events})
            measured: dict[tuple[str, date], Decimal] = {}
            for i, (key_id, day) in enumerate(todo, 1):
                try:
                    rate = measure_usd_per_hour(client, pid, key_id, day)
                except httpx.HTTPError as exc:
                    log(f"  [{i}/{len(todo)}] {day} {key_names.get(key_id, key_id)}: error {type(exc).__name__}")
                    continue
                if rate is not None:
                    measured[(key_id, day)] = rate
            events += apply_measured_rates(project_events, measured)
            project_balance = fetch_balance(client, pid)
            balance += project_balance
            log(f"Saldo Deepgram ({project.get('name')}): ${project_balance:,.2f} USD")
            catalog += [
                ProviderResource(provider=Provider.DEEPGRAM, kind=ResourceKind.API_KEY, resource_key=key_id,
                                 name=name or key_id, group_name=project.get("name"))
                for key_id, name in key_names.items()
            ]
        return events, catalog, balance


def main() -> None:
    from collections import Counter

    from config.settings import get_settings
    from repositories import get_repositories

    parser = argparse.ArgumentParser(description="Sincroniza horas y costo por API key de Deepgram")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true", help="descarga y resume, no guarda en Supabase")
    parser.add_argument("--usd-per-min", type=Decimal,
                        help="tarifa a usar en vez de la tabla rates (solo para estimar en --dry-run)")
    parser.add_argument("--since", type=date.fromisoformat, help="fecha inicial YYYY-MM-DD (ignora --days)")
    args = parser.parse_args()

    api_key = get_settings().deepgram_api_key.get_secret_value()
    if not api_key:
        raise SystemExit("Falta DEEPGRAM_API_KEY en .env")
    if args.usd_per_min is not None:
        if not args.dry_run:
            raise SystemExit("--usd-per-min solo con --dry-run; para guardar, carga la tarifa en la tabla rates")
        rates = [Rate(provider=Provider.DEEPGRAM, model="*", unit=UsageUnit.AUDIO_SECONDS,
                      price_usd=args.usd_per_min, per_units=60, effective_from=date(2000, 1, 1))]
    else:
        rates = get_repositories().rates.list()

    end = datetime.now(timezone.utc).date()
    events, catalog, balance = fetch_events(api_key, args.since or end - timedelta(days=args.days), end, rates)
    saved = 0
    if not args.dry_run:
        repos = get_repositories()
        repos.resources.upsert_catalog(catalog)
        saved = repos.usage.upsert_many(events)
        repos.balances.insert("deepgram", balance)
    print(f"Catálogo: {len(catalog)} API keys")

    hours, usd = Counter(), Counter()
    for e in events:
        hours[e.metadata["key_name"]] += float(e.quantities[UsageUnit.AUDIO_SECONDS]) / 3600
        usd[e.metadata["key_name"]] += float(e.cost_usd)
    missing = sum(1 for e in events if e.metadata.get("missing_rates"))
    print(f"{len(events)} registros día×key×modelo · guardados {saved}{' (dry-run)' if args.dry_run else ''}")
    if missing:
        print(f"  ATENCIÓN: {missing} registros sin tarifa en `rates` → costo 0")
    for name, h in hours.most_common():
        print(f"  {h:>9,.2f} h  {usd[name]:>10,.2f} USD  {name}")


if __name__ == "__main__":
    main()
