"""Marca activo/inactivo cada recurso del catálogo según su gasto de los últimos días.

Solo cambia el catálogo del dashboard (provider_resources.active): no toca nada en los proveedores ni la
campaña asignada. Un recurso inactivo que vuelve a gastar se reactiva en la siguiente corrida.

Uso:  python -m integrations.refresh_activity [--days 15] [--dry-run]
"""

import argparse
from datetime import datetime, timedelta, timezone

from services.activity import ACTIVITY_DAYS, active_resource_keys


def main() -> None:
    from repositories import get_repositories

    parser = argparse.ArgumentParser(description="Activa/desactiva recursos del catálogo según su actividad")
    parser.add_argument("--days", type=int, default=ACTIVITY_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repos = get_repositories()
    now = datetime.now(timezone.utc)
    active = active_resource_keys(repos.usage.list(now - timedelta(days=args.days), now))
    resources = repos.resources.list()
    to_on = {r.id for r in resources if (str(r.provider), r.resource_key) in active and not r.active}
    to_off = {r.id for r in resources if (str(r.provider), r.resource_key) not in active and r.active}
    if not args.dry_run:
        repos.resources.set_active(to_on, True)
        repos.resources.set_active(to_off, False)
    total_active = sum(1 for r in resources if (str(r.provider), r.resource_key) in active)
    print(f"Actividad {args.days} días: {total_active} activos de {len(resources)} · reactivados {len(to_on)} · "
          f"desactivados {len(to_off)}{' (dry-run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
