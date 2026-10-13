"""Estado de presupuesto mensual por campaña y proyección a fin de mes."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class BudgetStatus(StrEnum):
    NO_BUDGET = "no_budget"
    OK = "ok"
    WARNING = "warning"
    EXCEEDED = "exceeded"


@dataclass
class BudgetResult:
    status: BudgetStatus
    spent_usd: Decimal
    budget_usd: Decimal | None
    ratio: Decimal | None
    remaining_usd: Decimal | None


def evaluate_budget(spent: Decimal, budget: Decimal | None, warning_ratio: Decimal = Decimal("0.8")) -> BudgetResult:
    if not budget or budget <= 0:
        return BudgetResult(BudgetStatus.NO_BUDGET, spent, None, None, None)
    ratio = spent / budget
    if ratio >= 1:
        status = BudgetStatus.EXCEEDED
    elif ratio >= warning_ratio:
        status = BudgetStatus.WARNING
    else:
        status = BudgetStatus.OK
    return BudgetResult(status, spent, budget, ratio, budget - spent)


def forecast_month_end(spent_to_date: Decimal, day_of_month: int, days_in_month: int) -> Decimal:
    """Proyección lineal: gasto diario promedio × días del mes."""
    if day_of_month <= 0:
        raise ValueError("day_of_month debe ser >= 1")
    return spent_to_date / day_of_month * days_in_month


def limit_in_usd(limit_amount: Decimal, currency: str, usd_mxn_rate: float | None) -> Decimal:
    if currency == "USD":
        return limit_amount
    if currency == "MXN":
        if not usd_mxn_rate:
            raise ValueError("Tope en MXN requiere USD_MXN_RATE")
        return limit_amount / Decimal(str(usd_mxn_rate))
    raise ValueError(f"moneda no soportada: {currency}")


def evaluate_alert(spent_usd: Decimal, alert, usd_mxn_rate: float | None) -> BudgetResult:
    """Evalúa una BudgetAlert (tope en USD o MXN) contra el gasto en USD. Alerta inactiva → NO_BUDGET."""
    if alert is None or not alert.active:
        return evaluate_budget(spent_usd, None)
    limit = limit_in_usd(alert.limit_amount, alert.currency, usd_mxn_rate)
    return evaluate_budget(spent_usd, limit, alert.warning_pct)
