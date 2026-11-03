import calendar
from datetime import datetime, time
from decimal import Decimal

import pandas as pd
import plotly.express as px
import streamlit as st

from config.settings import get_settings
from pages.common import billing_alerts_banner, demo_banner, load_usage, money, period_picker, repos, style_fig, theme_mode, today_local
from services.budget_service import BudgetStatus, evaluate_alert, forecast_month_end
from services.chart_theme import STATUS, UNASSIGNED, campaign_color_map, display_name

settings = get_settings()
currency = settings.default_display_currency
rate = settings.display_rate
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]

st.title("Dashboard")
demo_banner()
billing_alerts_banner()

start, end = period_picker()
campaigns = repos().campaigns.list()
colors = campaign_color_map(campaigns, theme_mode())
order = [c.name for c in sorted(campaigns, key=lambda c: (c.created_at is None, c.created_at or 0, c.name))]

df = load_usage(start, end)
df["campaña"] = df["campaign"].map(lambda n: display_name(n, colors))

# --- Filtros (una fila, sobre las gráficas) ---------------------------------------------------------------
present = [n for n in [*order, "Otras campañas", UNASSIGNED] if n in set(df["campaña"])]
f1, f2 = st.columns([3, 2])
picked = f1.multiselect("Campañas", present, placeholder="Todas las campañas")
providers_all = sorted(df["provider"].unique())
providers = f2.pills("Proveedor", providers_all, selection_mode="multi", default=providers_all)
if picked:
    df = df[df["campaña"].isin(picked)]
if providers:
    df = df[df["provider"].isin(providers)]

# --- Indicadores ------------------------------------------------------------------------------------------
days = max((end - start).days, 1)
total_usd = df["cost_usd"].sum()
unassigned_usd = df.loc[df["campaign"] == UNASSIGNED, "cost_usd"].sum()
with st.container(horizontal=True):
    st.metric("Gasto del periodo", money(total_usd), border=True)
    st.metric("Promedio diario", money(total_usd / days), border=True)
    st.metric("Sin campaña asignada", money(unassigned_usd),
              f"{unassigned_usd / total_usd:.0%} del total" if total_usd else None, delta_color="off",
              border=True, help="Gasto de recursos que aún no asignas a una campaña (página Campañas).")

# --- ¿De qué es el gasto sin campaña? ---------------------------------------------------------------------
PROVIDER_LABEL = {"openai": "OpenAI", "deepgram": "Deepgram", "elevenlabs": "ElevenLabs", "anthropic": "Anthropic"}
unassigned_df = df[df["campaign"] == UNASSIGNED]
if unassigned_usd > 0:
    with st.expander(f"⚠️ ¿De qué es el gasto sin campaña? · {money(unassigned_usd)}", expanded=True):
        breakdown = (unassigned_df.assign(recurso=unassigned_df["agent"].fillna("(sin identificar)"))
                     .groupby(["provider", "recurso"])["cost"].sum().reset_index()
                     .sort_values("cost", ascending=False))
        breakdown = breakdown[breakdown["cost"] > 0.005]
        breakdown["provider"] = breakdown["provider"].map(PROVIDER_LABEL).fillna(breakdown["provider"])
        breakdown["share"] = breakdown["cost"] / breakdown["cost"].sum() * 100
        by_prov = breakdown.groupby("provider")["cost"].sum().sort_values(ascending=False)
        st.markdown(" · ".join(f"**{p}** ${v:,.2f} {currency}" for p, v in by_prov.items()))
        st.dataframe(
            breakdown.rename(columns={"provider": "Proveedor", "recurso": "API key / agente",
                                      "cost": f"Gasto ({currency})", "share": "% del gasto sin campaña"}),
            hide_index=True,
            width="stretch",
            column_config={
                f"Gasto ({currency})": st.column_config.NumberColumn(format="$%,.2f"),
                "% del gasto sin campaña": st.column_config.ProgressColumn(format="%.1f%%", min_value=0,
                                                                          max_value=100),
            },
        )
        st.caption("Asigna estos recursos a una campaña en la página **Campañas** para que dejen de aparecer aquí.")

if df.empty:
    st.info("Sin gasto en el periodo y filtros seleccionados.")
else:
    # --- Gasto diario por campaña -------------------------------------------------------------------------
    with st.container(border=True):
        st.markdown("**Gasto diario por campaña**")
        daily = (df.assign(día=df["occurred_at"].dt.tz_convert(settings.app_timezone).dt.date)
                 .groupby(["día", "campaña"])["cost"].sum().reset_index())
        fig = px.bar(daily, x="día", y="cost", color="campaña", color_discrete_map=colors,
                     category_orders={"campaña": present},
                     custom_data=["campaña"])
        fig.update_traces(hovertemplate=f"%{{x|%d %b}} · %{{customdata[0]}}<br><b>$%{{y:,.2f}} {currency}</b><extra></extra>")
        fig = style_fig(fig)
        # Eje siempre en días: con pocos días Plotly mostraba horas/milisegundos ("23:59:59.9996").
        fig.update_xaxes(type="date", tickformat="%d %b", dtick=86_400_000,
                         range=[pd.Timestamp(start.date()) - pd.Timedelta(hours=12),
                                pd.Timestamp((end - pd.Timedelta(days=1)).date()) + pd.Timedelta(hours=12)])
        st.plotly_chart(fig, width="stretch")

    # --- Total por campaña (clic = detalle) ---------------------------------------------------------------
    with st.container(border=True):
        st.markdown("**Gasto por campaña en el periodo** · haz clic en una barra para ver su detalle")
        totals = df.groupby("campaña")["cost"].sum().reset_index().sort_values("cost")
        fig = px.bar(totals, x="cost", y="campaña", orientation="h", color="campaña", color_discrete_map=colors,
                     text=totals["cost"].map(lambda v: f"${v:,.0f}"))
        fig.update_traces(hovertemplate=f"%{{y}}<br><b>$%{{x:,.2f}} {currency}</b><extra></extra>",
                          textposition="outside", cliponaxis=False)
        fig.update_layout(showlegend=False)
        fig = style_fig(fig, height=max(220, 52 * len(totals)))
        fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)")
        fig.update_yaxes(showgrid=False)
        event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points",
                                key="by_campaign")

        points = event.selection.points if event and event.selection else []
        if points:
            selected = points[0].get("y")
            detail = df[df["campaña"] == selected]
            st.markdown(f"##### Detalle: {selected}")
            d1, d2 = st.columns(2)
            by_provider = detail.groupby("provider")["cost"].sum().reset_index().sort_values("cost", ascending=False)
            d1.dataframe(by_provider.rename(columns={"provider": "Proveedor", "cost": f"Gasto ({currency})"}),
                         hide_index=True, width="stretch",
                         column_config={f"Gasto ({currency})": st.column_config.NumberColumn(format="$%,.2f")})
            by_resource = (detail.assign(recurso=detail["agent"].fillna(detail["model"]))
                           .groupby(["provider", "recurso"])["cost"].sum().reset_index()
                           .sort_values("cost", ascending=False))
            d2.dataframe(by_resource.rename(columns={"provider": "Proveedor", "recurso": "Agente / API key",
                                                     "cost": f"Gasto ({currency})"}),
                         hide_index=True, width="stretch",
                         column_config={f"Gasto ({currency})": st.column_config.NumberColumn(format="$%,.2f")})

# --- Alertas de presupuesto (siempre mes en curso, todos los proveedores) -----------------------------------
today = today_local()
st.subheader(f"Presupuesto de {MONTHS[today.month - 1]} {today.year}")
st.caption("Compara el gasto del mes en curso contra el tope de cada campaña (catálogo en la página Alertas). "
           "No depende del periodo ni de los filtros de arriba.")

alerts = {a.campaign_id: a for a in repos().alerts.list()}
month_start = datetime.combine(today.replace(day=1), time.min, tzinfo=settings.tz)
month_df = load_usage(month_start, datetime.now(settings.tz))
spent_by_campaign = month_df.groupby("campaign_id")["cost_usd"].sum().to_dict() if len(month_df) else {}
days_in_month = calendar.monthrange(today.year, today.month)[1]

rows = []
for campaign in campaigns:
    alert = alerts.get(campaign.id)
    spent = Decimal(str(spent_by_campaign.get(str(campaign.id), 0)))
    result = evaluate_alert(spent, alert, settings.usd_mxn_rate)
    icon, label, _ = STATUS[result.status.value]
    rows.append({
        "Estado": f"{icon} {label}",
        "Campaña": campaign.name,
        f"Gastado ({currency})": float(spent) * rate,
        f"Tope ({currency})": float(result.budget_usd) * rate if result.budget_usd else None,
        "% usado": float(result.ratio * 100) if result.ratio is not None else None,
        f"Proyección fin de mes ({currency})": float(forecast_month_end(spent, today.day, days_in_month)) * rate,
        "_status": result.status.value,
    })

over = [r for r in rows if r["_status"] == BudgetStatus.EXCEEDED]
near = [r for r in rows if r["_status"] == BudgetStatus.WARNING]
for r in over:
    st.error(f"🔴 **{r['Campaña']}** alcanzó su tope: ${r[f'Gastado ({currency})']:,.2f} de "
             f"${r[f'Tope ({currency})']:,.2f} {currency} ({r['% usado']:.0f}%).")
for r in near:
    st.warning(f"🟠 **{r['Campaña']}** está cerca del tope: {r['% usado']:.0f}% usado.")

if rows:
    table = pd.DataFrame(rows).sort_values("% usado", ascending=False, na_position="last")
    status_col = table.pop("_status")

    def highlight(row):
        if status_col[row.name] == BudgetStatus.EXCEEDED:
            return ["background-color: rgba(208,59,59,0.16); color: #d03b3b; font-weight: 600"] * len(row)
        if status_col[row.name] == BudgetStatus.WARNING:
            return ["background-color: rgba(250,178,25,0.16)"] * len(row)
        return [""] * len(row)

    money_fmt = st.column_config.NumberColumn(format="$%,.2f")
    st.dataframe(
        table.style.apply(highlight, axis=1),
        hide_index=True,
        width="stretch",
        column_config={
            f"Gastado ({currency})": money_fmt,
            f"Tope ({currency})": money_fmt,
            f"Proyección fin de mes ({currency})": money_fmt,
            "% usado": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
        },
    )
    if not alerts:
        st.caption("Aún no hay topes definidos. Configúralos en la página **Alertas**.")
else:
    st.info("No hay campañas. Créalas en la página **Campañas**.")
