"""Alertas de pagos y saldos: facturas por pagar y cuándo se agota el saldo prepagado de cada proveedor."""

from dataclasses import dataclass
from datetime import date, timedelta

WARNING_DAYS = 7
CRITICAL_DAYS = 3
PROVIDER_LABEL = {"openai": "OpenAI", "elevenlabs": "ElevenLabs", "deepgram": "Deepgram", "anthropic": "Anthropic"}


@dataclass
class BillingAlert:
    provider: str
    level: str  # "critical" | "warning" | "ok"
    title: str
    detail: str
    amount_usd: float | None = None
    days_left: float | None = None
    runs_out_on: date | None = None

    @property
    def icon(self) -> str:
        return {"critical": "🔴", "warning": "🟠", "ok": "🟢"}[self.level]


def invoice_alert(provider: str, invoices: list[dict]) -> BillingAlert | None:
    """Facturas abiertas sin marcar como pagadas. Cuenta vencida (past_due) → crítica."""
    pending = [i for i in invoices if not i.get("paid_order_id")]
    if not pending:
        return None
    total = sum(float(i["amount_usd"]) for i in pending)
    overdue = any(i.get("account_status") == "past_due" for i in pending)
    return BillingAlert(
        provider=provider,
        level="critical" if overdue else "warning",
        title=f"{PROVIDER_LABEL[provider]}: {len(pending)} factura(s) por pagar · ${total:,.2f} USD",
        detail=("Cuenta vencida: el proveedor puede suspender el servicio." if overdue
                else "Pendiente de pago."),
        amount_usd=total,
    )


def balance_alert(provider: str, balance_usd: float | None, daily_usd: float, today: date,
                  warning_days: int = WARNING_DAYS, critical_days: int = CRITICAL_DAYS) -> BillingAlert | None:
    """Días que alcanza el saldo al ritmo de consumo diario. Sin saldo conocido → None."""
    if balance_usd is None:
        return None
    if balance_usd <= 0:
        return BillingAlert(provider, "critical", f"{PROVIDER_LABEL[provider]}: saldo agotado",
                            f"Saldo ${balance_usd:,.2f} USD: recarga para evitar cortes.", balance_usd, 0, today)
    if daily_usd <= 0:
        return BillingAlert(provider, "ok", f"{PROVIDER_LABEL[provider]}: saldo ${balance_usd:,.2f} USD",
                            "Sin consumo reciente.", balance_usd)
    days = balance_usd / daily_usd
    runs_out = today + timedelta(days=int(days))
    level = "critical" if days < critical_days else "warning" if days < warning_days else "ok"
    return BillingAlert(
        provider=provider,
        level=level,
        title=f"{PROVIDER_LABEL[provider]}: saldo para {days:,.1f} días (≈ {runs_out:%d %b})",
        detail=f"Saldo ${balance_usd:,.2f} USD · consumo ${daily_usd:,.2f} USD/día (promedio 7 días).",
        amount_usd=balance_usd,
        days_left=days,
        runs_out_on=runs_out,
    )


def projected_balance(captured_usd: float, consumed_since_usd: float) -> float:
    """Saldo capturado a mano (OpenAI) menos lo consumido desde esa fecha."""
    return captured_usd - consumed_since_usd
