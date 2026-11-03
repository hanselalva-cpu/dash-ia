from datetime import date

from services.billing_alerts import balance_alert, invoice_alert, projected_balance

TODAY = date(2026, 11, 3)


def test_overdue_invoices_are_critical_and_paid_ones_ignored():
    invoices = [
        {"amount_usd": 20700.0, "account_status": "past_due", "paid_order_id": None},
        {"amount_usd": 25549.25, "account_status": "past_due", "paid_order_id": None},
        {"amount_usd": 999.0, "account_status": "past_due", "paid_order_id": "manual-1"},
    ]
    a = invoice_alert("elevenlabs", invoices)
    assert a.level == "critical" and a.amount_usd == 46249.25 and "2 factura" in a.title


def test_no_pending_invoices_no_alert():
    assert invoice_alert("elevenlabs", [{"amount_usd": 1, "paid_order_id": "x"}]) is None
    assert invoice_alert("elevenlabs", []) is None


def test_balance_days_and_levels():
    a = balance_alert("deepgram", 280.0, 42.19, TODAY)
    assert a.level == "warning" and round(a.days_left, 1) == 6.6 and a.runs_out_on == date(2026, 11, 9)
    assert balance_alert("deepgram", 100.0, 42.19, TODAY).level == "critical"  # 2.4 días
    assert balance_alert("deepgram", 1000.0, 42.19, TODAY).level == "ok"
    assert balance_alert("deepgram", 0.0, 42.19, TODAY).level == "critical"
    assert balance_alert("deepgram", None, 42.19, TODAY) is None


def test_openai_projected_balance():
    assert projected_balance(500.0, 120.5) == 379.5
