"""Pagos vs. consumo por proveedor: cuándo depositamos/pagamos y cuándo consumimos."""

from datetime import datetime, time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.settings import get_settings
from pages.common import demo_banner, load_usage, period_picker, repos, style_fig, today_local
from services.chart_theme import CATEGORICAL_LIGHT

settings = get_settings()
currency = settings.default_display_currency
rate = settings.display_rate
PROVIDERS = {"openai": "OpenAI", "elevenlabs": "ElevenLabs", "deepgram": "Deepgram", "anthropic": "Anthropic"}
MONEY = st.column_config.NumberColumn(format="$%,.2f")


def fmt(v: float) -> str:
    return f"{'-' if v < 0 else ''}${abs(v):,.2f} {currency}"


st.title("Pagos vs. consumo")
demo_banner()
st.caption("Recargas de **Deepgram**: llegan solas en cada sincronización. **OpenAI y ElevenLabs** no exponen sus "
           "pagos por API: regístralos aquí (recargas de créditos, facturas pagadas).")

start, end = period_picker(key="pay")
days = max((end - start).days, 1)

# --- Registrar pago manual ----------------------------------------------------------------------------------
with st.expander("➕ Registrar pago (OpenAI, ElevenLabs u otro)"):
    with st.form("new_payment", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.8])
        provider = c1.selectbox("Proveedor", ["openai", "elevenlabs", "deepgram", "anthropic"],
                                format_func=PROVIDERS.get)
        paid_on = c2.date_input("Fecha de pago", today_local(), format="DD/MM/YYYY")
        amount = c3.number_input("Monto", min_value=0.0, step=100.0, format="%.2f")
        cur = c4.selectbox("Moneda", ["USD", "MXN"])
        note = st.text_input("Nota", placeholder="Ej. Factura agosto, recarga de créditos, pago con tarjeta…")
        if st.form_submit_button("Guardar pago", type="primary", disabled=repos().demo):
            if amount <= 0:
                st.error("El monto debe ser mayor a 0.")
            elif cur == "MXN" and not settings.usd_mxn_rate:
                st.error("Para registrar en MXN se necesita USD_MXN_RATE.")
            else:
                usd = amount / settings.usd_mxn_rate if cur == "MXN" else amount
                paid_at = datetime.combine(paid_on, time(12), tzinfo=settings.tz)
                repos().balances.add_manual_payment(provider, paid_at, amount, cur, usd, note.strip())
                st.toast(f"Pago de {PROVIDERS[provider]} registrado", icon="✅")
                st.rerun()

# --- Datos ---------------------------------------------------------------------------------------------------
payments = pd.DataFrame(repos().balances.purchases())
usage = load_usage(start, end)
if payments.empty and usage.empty:
    st.info("Sin pagos ni consumo en el periodo.")
    st.stop()
if not payments.empty:
    payments["created_at"] = pd.to_datetime(payments["created_at"], utc=True)
    payments["monto"] = payments["amount_usd"].astype(float) * rate
    payments["source"] = payments.get("source", pd.Series("api", index=payments.index)).fillna("api")
    in_period = payments[(payments["created_at"] >= pd.Timestamp(start)) & (payments["created_at"] < pd.Timestamp(end))]
else:
    in_period = payments

balances = {p: repos().balances.history(p, start - pd.Timedelta(days=60)) for p in ["deepgram"]}

# --- Cuadre por proveedor -----------------------------------------------------------------------------------
st.subheader("Cuadre del periodo")
cards = st.columns(3)
for col, prov in zip(cards, ["elevenlabs", "openai", "deepgram"]):
    paid = in_period.loc[in_period["provider"] == prov, "monto"].sum() if not in_period.empty else 0.0
    used = usage.loc[usage["provider"] == prov, "cost"].sum() if not usage.empty else 0.0
    with col.container(border=True):
        st.markdown(f"**{PROVIDERS[prov]}**")
        st.metric("Pagado / depositado", fmt(paid))
        st.metric("Consumido", fmt(used), f"{used / days:,.2f} {currency}/día", delta_color="off")
        st.metric("Pagado − consumido", fmt(paid - used),
                  help="Positivo: pagaste más de lo que consumiste en el periodo (queda saldo o pagaste deuda "
                       "anterior). Negativo: consumiste más de lo pagado (se usó saldo previo o hay deuda).")
        if prov == "deepgram" and balances["deepgram"]:
            bal = float(balances["deepgram"][-1]["amount_usd"]) * rate
            st.caption(f"Saldo actual en cuenta: **{fmt(bal)}** · alcanza para ~{bal / (used / days):,.1f} días"
                       if used else f"Saldo actual en cuenta: **{fmt(bal)}**")
        if prov != "deepgram" and paid == 0:
            st.caption("Sin pagos registrados en el periodo: agrégalos arriba.")

# --- Acumulado: pagado vs. consumido en el tiempo ----------------------------------------------------------
st.subheader("Acumulado en el periodo")
tabs = st.tabs([PROVIDERS[p] for p in ["elevenlabs", "openai", "deepgram"]])
for tab, prov in zip(tabs, ["elevenlabs", "openai", "deepgram"]):
    with tab:
        all_days = pd.date_range(start.date(), (end - pd.Timedelta(days=1)).date(), freq="D")
        used = (usage[usage["provider"] == prov]
                .assign(día=lambda d: pd.to_datetime(d["occurred_at"].dt.tz_convert(settings.app_timezone).dt.date))
                .groupby("día")["cost"].sum().reindex(all_days, fill_value=0).cumsum()) if not usage.empty else None
        paid = (in_period[in_period["provider"] == prov]
                .assign(día=lambda d: pd.to_datetime(d["created_at"].dt.tz_convert(settings.app_timezone).dt.date))
                .groupby("día")["monto"].sum().reindex(all_days, fill_value=0).cumsum()) if not in_period.empty else None
        fig = go.Figure()
        if paid is not None:
            fig.add_scatter(x=paid.index, y=paid.values, name="Pagado acumulado", mode="lines",
                            line=dict(color=CATEGORICAL_LIGHT[2], width=2, shape="hv"))
        if used is not None:
            fig.add_scatter(x=used.index, y=used.values, name="Consumido acumulado", mode="lines",
                            line=dict(color=CATEGORICAL_LIGHT[1], width=2))
        fig.update_traces(hovertemplate=f"%{{x|%d %b}}<br><b>$%{{y:,.2f}} {currency}</b><extra>%{{fullData.name}}</extra>")
        fig = style_fig(fig, height=320)
        fig.update_layout(hovermode="x unified")
        fig.update_xaxes(type="date", tickformat="%d %b")
        st.plotly_chart(fig, width="stretch", key=f"cum_{prov}")

# --- Historial de pagos -------------------------------------------------------------------------------------
st.subheader("Historial de pagos")
if payments.empty:
    st.caption("Sin pagos registrados.")
else:
    hist = payments.sort_values("created_at", ascending=False).assign(
        Fecha=lambda d: d["created_at"].dt.tz_convert(settings.app_timezone).dt.strftime("%d %b %Y"),
        Proveedor=lambda d: d["provider"].map(PROVIDERS),
        Origen=lambda d: d["source"].map({"api": "Automático (API)", "manual": "Registrado a mano"}),
        Nota=lambda d: d.get("note", pd.Series(None, index=d.index)).fillna(""),
        **{"En el periodo": lambda d: (d["created_at"] >= pd.Timestamp(start)) & (d["created_at"] < pd.Timestamp(end))},
    )
    event = st.dataframe(
        hist[["Fecha", "Proveedor", "monto", "Origen", "Nota", "En el periodo"]].rename(columns={"monto": f"Monto ({currency})"}),
        hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key="pay_hist",
        column_config={f"Monto ({currency})": MONEY, "En el periodo": st.column_config.CheckboxColumn()})
    rows = hist.iloc[event.selection.rows] if event and event.selection.rows else hist.iloc[0:0]
    manual = rows[rows["source"] == "manual"]
    if len(rows):
        if manual.empty:
            st.caption("Las recargas automáticas no se pueden borrar (vienen de la API del proveedor).")
        elif st.button(f"🗑️ Borrar {len(manual)} pago(s) registrado(s) a mano", disabled=repos().demo):
            for _, r in manual.iterrows():
                repos().balances.delete_manual_payment(r["provider"], r["order_id"])
            st.toast("Pago(s) borrado(s)", icon="🗑️")
            st.rerun()
    st.caption("Selecciona filas para borrar pagos registrados a mano.")
