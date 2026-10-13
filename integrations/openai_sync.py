"""Descarga el costo diario por API key de OpenAI desde /v1/organization/costs (requiere Admin key).

El monto es el que factura OpenAI (USD), no se recalcula con `rates`. Un registro por día × key × line_item.
Idempotente: external_id = "cost:<día>:<project_id>:<api_key_id>:<line_item>".

Uso:  python -m integrations.openai_sync --days 30 [--dry-run]
"""

import argparse
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from integrations._common import day_anchor
from models.schemas import Provider, ProviderResource, ResourceKind, UsageEvent, UsageSource

BASE_URL = "https://api.openai.com"
NO_KEY = "Sin API key"


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


def fetch_key_names(client: httpx.Client) -> dict[str, dict]:
    """api_key_id → {name, project_id, project_name}."""
    names = {}
    projects = _get(client, "/v1/organization/projects", {"limit": 100, "include_archived": "true"})["data"]
    for project in projects:
        params = {"limit": 100}
        while True:
            page = _get(client, f"/v1/organization/projects/{project['id']}/api_keys", params)
            for key in page["data"]:
                names[key["id"]] = {"name": key.get("name"), "project_id": project["id"],
                                    "project_name": project.get("name")}
            if not page.get("has_more"):
                break
            params["after"] = page["last_id"]
    return names


def fetch_cost_buckets(client: httpx.Client, start: datetime, end: datetime):
    params = {
        "start_time": int(start.timestamp()),
        "end_time": int(end.timestamp()),
        "bucket_width": "1d",
        "group_by": ["project_id", "api_key_id", "line_item"],
        "limit": 31,
    }
    while True:
        page = _get(client, "/v1/organization/costs", params)
        yield from page["data"]
        if not page.get("has_more") or not page.get("next_page"):
            return
        params["page"] = page["next_page"]


def build_events(buckets, key_names: dict[str, dict]) -> list[UsageEvent]:
    events = []
    for bucket in buckets:
        day = datetime.fromtimestamp(bucket["start_time"], tz=timezone.utc)
        for res in bucket.get("results", []):
            amount = Decimal(str((res.get("amount") or {}).get("value") or 0))
            if not amount:
                continue
            key_id = res.get("api_key_id")
            info = key_names.get(key_id, {})
            line_item = res.get("line_item") or "unknown"
            project_id = res.get("project_id") or info.get("project_id")
            events.append(UsageEvent(
                occurred_at=day_anchor(day),
                provider=Provider.OPENAI,
                model=line_item,
                cost_usd=amount.quantize(Decimal("0.00000001")),
                source=UsageSource.PROVIDER_SYNC,
                external_id=f"cost:{day.date().isoformat()}:{project_id}:{key_id}:{line_item}",
                metadata={
                    "openai_api_key_id": key_id,
                    "key_name": info.get("name") or (key_id or NO_KEY),
                    "project_id": project_id,
                    "project_name": res.get("project_name") or info.get("project_name"),
                    "line_item": line_item,
                    "granularity": "day",
                },
            ))
    return events


def build_catalog(key_names: dict[str, dict]) -> list[ProviderResource]:
    return [
        ProviderResource(provider=Provider.OPENAI, kind=ResourceKind.API_KEY, resource_key=key_id,
                         name=info.get("name") or key_id, group_name=info.get("project_name"))
        for key_id, info in key_names.items()
    ]


def fetch_events(admin_key: str, start: datetime, end: datetime) -> tuple[list[UsageEvent], list[ProviderResource]]:
    with httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {admin_key}"}, timeout=60) as client:
        key_names = fetch_key_names(client)
        return build_events(fetch_cost_buckets(client, start, end), key_names), build_catalog(key_names)


def main() -> None:
    from collections import Counter

    from config.settings import get_settings
    from repositories import get_repositories

    parser = argparse.ArgumentParser(description="Sincroniza costo diario por API key de OpenAI")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--since", type=date.fromisoformat, help="fecha inicial YYYY-MM-DD (ignora --days)")
    parser.add_argument("--dry-run", action="store_true", help="descarga y resume, no guarda en Supabase")
    args = parser.parse_args()

    admin_key = get_settings().openai_usage_key
    if not admin_key:
        raise SystemExit("Falta Admin key de OpenAI (sk-admin-) en OPENAI_ADMIN_KEY u OPENAI_API_KEY")
    end = datetime.now(timezone.utc)
    start = (datetime.combine(args.since, datetime.min.time(), tzinfo=timezone.utc) if args.since
             else end - timedelta(days=args.days))

    events, catalog = fetch_events(admin_key, start, end)
    saved = 0
    if not args.dry_run:
        repos = get_repositories()
        repos.resources.upsert_catalog(catalog)
        saved = repos.usage.upsert_many(events)
    print(f"Catálogo: {len(catalog)} API keys")

    total = Counter()
    for e in events:
        total[e.metadata["key_name"]] += float(e.cost_usd)
    print(f"{len(events)} registros día×key×concepto · guardados {saved}{' (dry-run)' if args.dry_run else ''}")
    for name, usd in total.most_common():
        print(f"  {usd:>12,.2f} USD  {name}")


if __name__ == "__main__":
    main()
