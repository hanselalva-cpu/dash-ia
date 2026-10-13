"""Cálculo de costo de un evento de uso a partir de tarifas versionadas por fecha."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from models.schemas import Provider, Rate, UsageEvent, UsageUnit

COST_PRECISION = Decimal("0.00000001")


@dataclass
class CostLine:
    unit: UsageUnit
    quantity: Decimal
    rate: Rate
    cost_usd: Decimal


@dataclass
class CostBreakdown:
    lines: list[CostLine] = field(default_factory=list)
    missing_units: list[UsageUnit] = field(default_factory=list)

    @property
    def total_usd(self) -> Decimal:
        return sum((line.cost_usd for line in self.lines), Decimal(0)).quantize(COST_PRECISION)

    @property
    def complete(self) -> bool:
        return not self.missing_units


def find_rate(rates: list[Rate], provider: Provider, model: str, unit: UsageUnit, at: date) -> Rate | None:
    """Tarifa vigente en `at`. Prioriza modelo exacto sobre comodín "*", luego la más reciente."""
    candidates = [
        r
        for r in rates
        if r.provider == provider
        and r.unit == unit
        and r.model in (model, "*")
        and r.effective_from <= at
        and (r.effective_to is None or at < r.effective_to)
    ]
    return max(candidates, key=lambda r: (r.model == model, r.effective_from), default=None)


def calculate_cost(event: UsageEvent, rates: list[Rate]) -> CostBreakdown:
    breakdown = CostBreakdown()
    at = event.occurred_at.date()
    for unit, quantity in event.quantities.items():
        if not quantity:
            continue
        rate = find_rate(rates, event.provider, event.model, unit, at)
        if rate is None:
            breakdown.missing_units.append(unit)
            continue
        cost = Decimal(quantity) / Decimal(rate.per_units) * rate.price_usd
        breakdown.lines.append(CostLine(unit, Decimal(quantity), rate, cost.quantize(COST_PRECISION)))
    return breakdown
