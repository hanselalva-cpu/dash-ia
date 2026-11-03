"""Catálogo de alertas: tope mensual de gasto por campaña."""

from datetime import datetime, time
from decimal import Decimal
from uuid import UUID

import pandas as pd
import streamlit as st

from config.settings import get_settings
from models.schemas import BudgetAlert
from pages.common import billing_alerts, demo_banner, load_usage, repos, today_local
from services.budget_service import evaluate_alert
from services.chart_theme import STATUS

settings = get_settings()
CURRENCIES = ["MXN", "USD"] if settings.default_display_currency == "MXN" else ["USD", "MXN"]

st.title("Alertas")
demo_banner()

st.subheader("Pagos y saldos")
pay_alerts = billing_alerts()
if not pay_alerts:
    st.caption("Sin facturas abiertas ni saldos registrados.")
for a in pay_alerts:
    box = {"critical": st.error, "warning": st.warning, "ok": st.success}[a.level]
    box(f"{a.icon} **{a.title}** — {a.detail}")
st.page_link("pages/invoices.py", label="Facturas y saldos por pagar", icon="🧾")

st.subheader("Presupuesto por campaña")
st.caption("Define el tope mensual que cada campaña no debe pasar. Al llegar al % de aviso se marca en "
           "naranja; al llegar al tope, en rojo (Dashboard y aquí). Tope vacío o 0 = sin alerta.")

campaigns = [c for c in repos().campaigns.list() if c.status != "archived"]
if not campaigns:
    st.info("No hay campañas activas. Créalas en la página **Campañas**.")
    st.stop()

alerts = {a.campaign_id: a for a in repos().alerts.list()}
today = today_local()
month_df = load_usage(datetime.combine(today.replace(day=1), time.min, tzinfo=settings.tz), datetime.now(settings.tz))
spent = month_df.groupby("campaign_id")["cost_usd"].sum().to_dict() if len(month_df) else {}

rows = []
for c in campaigns:
    a = alerts.get(c.id)
    result = evaluate_alert(Decimal(str(spent.get(str(c.id), 0))), a, settings.usd_mxn_rate)
    icon, label, _ = STATUS[result.status.value]
    rows.append({
        "id": str(c.id),
        "Campaña": c.name,
        "Tope mensual": float(a.limit_amount) if a else None,
        "Moneda": a.currency if a else CURRENCIES[0],
        "Aviso al %": int(a.warning_pct * 100) if a else 80,
        "Activa": a.active if a else True,
        "Estado del mes": f"{icon} {label}" + (f" · {result.ratio:.0%}" if result.ratio is not None else ""),
    })

edited = st.data_editor(
    pd.DataFrame(rows),
    hide_index=True,
    width="stretch",
    disabled=["Campaña", "Estado del mes"],
    column_order=["Campaña", "Tope mensual", "Moneda", "Aviso al %", "Activa", "Estado del mes"],
    column_config={
        "Tope mensual": st.column_config.NumberColumn(min_value=0, step=100, format="$%,.2f",
                                                       help="Gasto máximo del mes para la campaña"),
        "Moneda": st.column_config.SelectboxColumn(options=["MXN", "USD"], required=True),
        "Aviso al %": st.column_config.NumberColumn(min_value=50, max_value=99, step=5, format="%d%%",
                                                     help="Porcentaje del tope en que se marca en naranja"),
        "Activa": st.column_config.CheckboxColumn(),
    },
    key="alerts_editor",
)

if st.button("Guardar alertas", type="primary", disabled=repos().demo):
    saved = removed = 0
    for row in edited.to_dict("records"):
        cid = UUID(row["id"])
        limit = row["Tope mensual"]
        if limit is None or pd.isna(limit) or limit <= 0:
            if cid in alerts:
                repos().alerts.delete(cid)
                removed += 1
            continue
        repos().alerts.save(BudgetAlert(
            campaign_id=cid,
            limit_amount=Decimal(str(round(limit, 2))),
            currency=row["Moneda"],
            warning_pct=Decimal(str(int(row["Aviso al %"]))) / 100,
            active=bool(row["Activa"]),
        ))
        saved += 1
    st.toast(f"Alertas guardadas: {saved} · eliminadas: {removed}", icon="✅")
    st.rerun()
