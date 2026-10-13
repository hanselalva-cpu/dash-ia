from decimal import Decimal

import pytest

from services.budget_service import BudgetStatus, evaluate_budget, forecast_month_end


@pytest.mark.parametrize(
    "spent,status",
    [("10", BudgetStatus.OK), ("80", BudgetStatus.WARNING), ("99.99", BudgetStatus.WARNING),
     ("100", BudgetStatus.EXCEEDED), ("150", BudgetStatus.EXCEEDED)],
)
def test_thresholds(spent, status):
    assert evaluate_budget(Decimal(spent), Decimal(100)).status == status


def test_no_budget():
    assert evaluate_budget(Decimal(5), None).status == BudgetStatus.NO_BUDGET
    assert evaluate_budget(Decimal(5), Decimal(0)).status == BudgetStatus.NO_BUDGET


def test_remaining():
    assert evaluate_budget(Decimal(30), Decimal(100)).remaining_usd == Decimal(70)


def test_forecast_linear():
    assert forecast_month_end(Decimal(10), 10, 30) == Decimal(30)


def test_forecast_invalid_day():
    with pytest.raises(ValueError):
        forecast_month_end(Decimal(1), 0, 30)


# --- Alertas con tope en USD o MXN ------------------------------------------------------------------------
from uuid import uuid4  # noqa: E402

from models.schemas import BudgetAlert  # noqa: E402
from services.budget_service import evaluate_alert, limit_in_usd  # noqa: E402


def _alert(limit, currency="USD", warning="0.8", active=True):
    return BudgetAlert(campaign_id=uuid4(), limit_amount=Decimal(limit), currency=currency,
                       warning_pct=Decimal(warning), active=active)


def test_mxn_limit_converted_with_rate():
    assert limit_in_usd(Decimal("18500"), "MXN", 18.5) == Decimal("1000")
    # 1,000 USD gastados contra tope de 18,500 MXN (=1,000 USD) → tope alcanzado
    assert evaluate_alert(Decimal(1000), _alert("18500", "MXN"), 18.5).status == BudgetStatus.EXCEEDED


def test_custom_warning_pct():
    assert evaluate_alert(Decimal(60), _alert("100", warning="0.6"), None).status == BudgetStatus.WARNING
    assert evaluate_alert(Decimal(59), _alert("100", warning="0.6"), None).status == BudgetStatus.OK


def test_inactive_or_missing_alert_is_no_budget():
    assert evaluate_alert(Decimal(999), _alert("10", active=False), None).status == BudgetStatus.NO_BUDGET
    assert evaluate_alert(Decimal(999), None, None).status == BudgetStatus.NO_BUDGET


def test_mxn_without_rate_fails_loudly():
    with pytest.raises(ValueError):
        limit_in_usd(Decimal(1), "MXN", None)
