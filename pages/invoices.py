"""Facturas abiertas y saldos por pagar de cada proveedor, con acceso al portal de pago."""

from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from config.settings import get_settings
from pages.common import demo_banner, load_usage, repos, today_local

settings = get_settings()
currency = settings.default_display_currency
rate = settings.display_rate
BILLING_URLS = {
    "elevenlabs": "https://elevenlabs.io/app/subscription",
    "deepgram": "https://console.deepgram.com/billing",
    "openai": "https://platform.openai.com/settings/organization/billing/overview",
}
PAYMENT_STATUS = {
    "requires_confirmation": "Pago pendiente de confirmar",
    "requires_payment_method": "Falta método de pago",
    "requires_action": "Requiere autenticación (3D Secure)",
    "processing": "Procesando",
    "succeeded": "Pagado",
}
ACCOUNT_STATUS = {"past_due": "🔴 Vencida (past_due)", "active": "🟢 Al corriente", "trialing": "Prueba"}


def usd_and_local(usd: float) -> str:
    return f"${usd:,.2f} USD" + (f" · ${usd * rate:,.2f} {currency}" if currency != "USD" else "")


st.title("Facturas y saldos por pagar")
demo_banner()
st.caption("El pago se hace en el portal de cada proveedor (tarjeta / autenticación): esta app no cobra ni guarda "
           "datos de pago. Después de pagar, márcala aquí para que quede en **Pagos** y en el cuadre.")

# --- ElevenLabs: facturas abiertas ---------------------------------------------------------------------------
st.subheader("ElevenLabs")
invoices = repos().balances.open_invoices("elevenlabs")
pending = [i for i in invoices if not i.get("paid_order_id")]
marked = [i for i in invoices if i.get("paid_order_id")]
if not invoices:
    st.success("Sin facturas abiertas en la última sincronización.")
else:
    account = invoices[0].get("account_status")
    captured = pd.to_datetime(invoices[0]["captured_at"]).tz_convert(settings.app_timezone).strftime("%d %b %Y %H:%M")
    total_pending = sum(float(i["amount_usd"]) for i in pending)
    with st.container(horizontal=True):
        st.metric("Por pagar", usd_and_local(total_pending), f"{len(pending)} factura(s)", delta_color="off", border=True)
        st.metric("Estado de la cuenta", ACCOUNT_STATUS.get(account, account or "—"), border=True)
    if account == "past_due" and pending:
        st.error("La suscripción de ElevenLabs está **vencida**. Si no se confirma el pago, ElevenLabs puede "
                 "suspender el servicio de los agentes.")
    st.link_button("💳 Pagar en ElevenLabs", BILLING_URLS["elevenlabs"], type="primary")

    for inv in invoices:
        amount = float(inv["amount_usd"])
        status = PAYMENT_STATUS.get((inv.get("payment_status") or "").split(",")[0].strip(), inv.get("payment_status") or "—")
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 2, 3], vertical_alignment="center")
            c1.markdown(f"**{usd_and_local(amount)}**")
            if inv.get("paid_order_id"):
                c2.markdown("✅ **Marcada como pagada**")
                c2.caption("Desaparece cuando ElevenLabs la cierre en la siguiente sincronización.")
                if c3.button("Deshacer", key=f"undo_{inv['invoice_key']}", disabled=repos().demo):
                    repos().balances.delete_manual_payment("elevenlabs", inv["paid_order_id"])
                    repos().balances.mark_invoice_paid("elevenlabs", inv["invoice_key"], None)
                    st.rerun()
            else:
                c2.markdown(f"🟠 {status}")
                with c3.popover("Marcar como pagada", disabled=repos().demo):
                    paid_on = st.date_input("Fecha de pago", today_local(), format="DD/MM/YYYY",
                                            key=f"date_{inv['invoice_key']}")
                    note = st.text_input("Nota", f"Factura ElevenLabs ${amount:,.2f} USD", key=f"note_{inv['invoice_key']}")
                    if st.button("Confirmar pago", type="primary", key=f"pay_{inv['invoice_key']}"):
                        order_id = repos().balances.add_manual_payment(
                            "elevenlabs", datetime.combine(paid_on, time(12), tzinfo=settings.tz),
                            amount, "USD", amount, note.strip())
                        repos().balances.mark_invoice_paid("elevenlabs", inv["invoice_key"], order_id)
                        st.toast("Factura marcada como pagada y registrada en Pagos", icon="✅")
                        st.rerun()
    st.caption(f"Facturas reportadas por la API de ElevenLabs al sincronizar ({captured}). La API no da número ni "
               "fecha de factura: por monto, ~$20,700 corresponde a agosto y ~$25,549 a septiembre.")

# --- Deepgram: saldo prepagado -------------------------------------------------------------------------------
st.subheader("Deepgram")
balances = repos().balances.history("deepgram", datetime.now(settings.tz) - timedelta(days=90))
if not balances:
    st.caption("Sin saldo registrado todavía (se guarda en cada sincronización).")
else:
    bal = float(balances[-1]["amount_usd"])
    week_start = datetime.combine(today_local() - timedelta(days=7), time.min, tzinfo=settings.tz)
    week = load_usage(week_start, datetime.combine(today_local(), time.min, tzinfo=settings.tz))
    daily_usd = week.loc[week["provider"] == "deepgram", "cost_usd"].sum() / 7 if not week.empty else 0
    days_left = bal / daily_usd if daily_usd else None
    with st.container(horizontal=True):
        st.metric("Saldo prepagado", usd_and_local(bal), border=True)
        st.metric("Consumo promedio (7 días)", f"${daily_usd:,.2f} USD/día", border=True)
        st.metric("Alcanza para", f"{days_left:,.1f} días" if days_left else "—", border=True)
    if days_left is not None and days_left < 7:
        st.warning(f"Al ritmo actual el saldo de Deepgram se acaba en **~{days_left:,.0f} días**. Recarga para evitar "
                   "cortes, o confirma que la recarga automática esté activa.")
    st.link_button("💳 Recargar en Deepgram", BILLING_URLS["deepgram"])

# --- OpenAI --------------------------------------------------------------------------------------------------
st.subheader("OpenAI")
st.caption("La API de OpenAI no expone facturas ni saldo de créditos (solo desde el navegador). Revisa ahí y "
           "registra los pagos en **Pagos**.")
st.link_button("💳 Facturación de OpenAI", BILLING_URLS["openai"])
