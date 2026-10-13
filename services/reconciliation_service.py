"""Conciliación: costo registrado por nosotros vs factura del proveedor, por mes."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from models.schemas import Provider


class ReconciliationStatus(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    MISSING_INVOICE = "missing_invoice"
    MISSING_USAGE = "missing_usage"


@dataclass
class ReconciliationLine:
    provider: Provider
    recorded_usd: Decimal
    invoiced_usd: Decimal | None
    diff_usd: Decimal | None
    diff_pct: Decimal | None
    status: ReconciliationStatus


def reconcile(
    recorded: dict[Provider, Decimal],
    invoiced: dict[Provider, Decimal],
    tolerance_pct: Decimal = Decimal("0.02"),
) -> list[ReconciliationLine]:
    """`diff = facturado - registrado`. Positivo = el proveedor cobra más de lo que medimos."""
    lines = []
    for provider in sorted(set(recorded) | set(invoiced)):
        rec = recorded.get(provider, Decimal(0))
        inv = invoiced.get(provider)
        if inv is None:
            lines.append(ReconciliationLine(provider, rec, None, None, None, ReconciliationStatus.MISSING_INVOICE))
            continue
        diff = inv - rec
        if rec == 0:
            status = ReconciliationStatus.MATCH if inv == 0 else ReconciliationStatus.MISSING_USAGE
            lines.append(ReconciliationLine(provider, rec, inv, diff, None, status))
            continue
        pct = diff / rec
        status = ReconciliationStatus.MATCH if abs(pct) <= tolerance_pct else ReconciliationStatus.MISMATCH
        lines.append(ReconciliationLine(provider, rec, inv, diff, pct, status))
    return lines
