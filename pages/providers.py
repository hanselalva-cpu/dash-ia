"""Gasto por proveedor: una pestaña por API con sus keys/agentes, campañas y desglose propio."""

import pandas as pd
import plotly.express as px
import streamlit as st

from config.settings import get_settings
from models.schemas import UsageUnit
from pages.common import demo_banner, load_usage, period_picker, repos, style_fig
from services.campaign_service import attribute_campaigns
from services.chart_theme import CATEGORICAL_LIGHT, NEUTRAL

settings = get_settings()
currency = settings.default_display_currency
rate = settings.display_rate
MONEY = st.column_config.NumberColumn(format="$%,.2f")
TOP_N = 7  # recursos con color propio en la gráfica; el resto se agrupa en "Otros"

st.title("Gasto por proveedor")
demo_banner()
start, end = period_picker(key="prov")
days = max((end - start).days, 1)

df = load_usage(start, end)
if df.empty:
    st.info("Sin gasto en el periodo seleccionado.")
    st.stop()
df["día"] = df["occurred_at"].dt.tz_convert(settings.app_timezone).dt.date
df["recurso"] = df["agent"].fillna("(sin identificar)")
total_all = df["cost"].sum()

# Cantidades (minutos de audio / horas) por evento, que to_dataframe no trae: se leen de los eventos crudos.
events = attribute_campaigns(repos().usage.list(start, end), repos().resources.list())
seconds = pd.DataFrame([
    {"provider": str(e.provider), "recurso": e.metadata.get("agent_name") or e.metadata.get("key_name"),
     "component": e.metadata.get("component"), "secs": float(e.quantities.get(UsageUnit.AUDIO_SECONDS, 0))}
    for e in events
])


def fmt(v: float) -> str:
    return f"${v:,.2f} {currency}"


def daily_by_resource(part: pd.DataFrame):
    top = part.groupby("recurso")["cost"].sum().sort_values(ascending=False).head(TOP_N).index.tolist()
    part = part.assign(serie=part["recurso"].where(part["recurso"].isin(top), "Otros"))
    daily = part.groupby(["día", "serie"])["cost"].sum().reset_index()
    color_map = {name: CATEGORICAL_LIGHT[i] for i, name in enumerate(top)} | {"Otros": NEUTRAL["light"]}
    fig = px.bar(daily, x="día", y="cost", color="serie", color_discrete_map=color_map,
                 category_orders={"serie": [*top, "Otros"]})
    fig.update_traces(hovertemplate=f"%{{x|%d %b}} · %{{fullData.name}}<br><b>$%{{y:,.2f}} {currency}</b><extra></extra>")
    fig = style_fig(fig)
    fig.update_xaxes(type="date", tickformat="%d %b", dtick=86_400_000 if days <= 31 else None)
    return fig


def resource_table(part: pd.DataFrame, extra: pd.DataFrame | None = None) -> pd.DataFrame:
    table = (part.groupby(["recurso", "campaign"])["cost"].sum().reset_index()
             .sort_values("cost", ascending=False))
    table = table[table["cost"] > 0.005]
    table["%"] = table["cost"] / table["cost"].sum() * 100 if len(table) else 0
    if extra is not None:
        table = table.merge(extra, on="recurso", how="left")
    return table.rename(columns={"recurso": "API key / agente", "campaign": "Campaña", "cost": f"Gasto ({currency})"})


def kpis(part: pd.DataFrame, label_extra: tuple[str, str] | None = None):
    total = part["cost"].sum()
    with st.container(horizontal=True):
        st.metric("Gasto del periodo", fmt(total), border=True)
        st.metric("Promedio diario", fmt(total / days), border=True)
        st.metric("% del gasto total", f"{total / total_all:.1%}" if total_all else "—", border=True)
        st.metric("Recursos con gasto", f"{part.loc[part['cost'] > 0.005, 'recurso'].nunique()}", border=True)
        if label_extra:
            st.metric(label_extra[0], label_extra[1], border=True)


tab_oa, tab_el, tab_dg = st.tabs(["🤖 OpenAI", "🎙️ ElevenLabs", "📝 Deepgram"])

# --- OpenAI ---------------------------------------------------------------------------------------------------
with tab_oa:
    part = df[df["provider"] == "openai"]
    if part.empty:
        st.info("Sin gasto de OpenAI en el periodo.")
    else:
        kpis(part)
        with st.container(border=True):
            st.markdown("**Gasto diario por API key**")
            st.plotly_chart(daily_by_resource(part), width="stretch", key="oa_daily")
        c1, c2 = st.columns([3, 2])
        with c1.container(border=True):
            st.markdown("**Por API key**")
            st.dataframe(resource_table(part), hide_index=True, width="stretch",
                         column_config={f"Gasto ({currency})": MONEY,
                                        "%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)})
        with c2.container(border=True):
            st.markdown("**Por modelo y concepto**")
            concept = part.assign(modelo=part["model"].str.split(",").str[0].str.strip(),
                                  concepto=part["model"].str.split(",").str[1].str.strip().fillna("—"))
            by_model = (concept.groupby(["modelo", "concepto"])["cost"].sum().reset_index()
                        .sort_values("cost", ascending=False))
            st.dataframe(by_model[by_model["cost"] > 0.005].rename(columns={"modelo": "Modelo", "concepto": "Concepto",
                                                                             "cost": f"Gasto ({currency})"}),
                         hide_index=True, width="stretch", column_config={f"Gasto ({currency})": MONEY})
        st.caption("Fuente: API de costos de OpenAI (monto facturado por día, key y concepto).")

# --- ElevenLabs -----------------------------------------------------------------------------------------------
with tab_el:
    part = df[df["provider"] == "elevenlabs"]
    if part.empty:
        st.info("Sin gasto de ElevenLabs en el periodo.")
    else:
        el_secs = seconds[(seconds["provider"] == "elevenlabs") & (seconds["component"] == "voice")]
        minutes = el_secs.groupby("recurso")["secs"].sum() / 60
        total_min = minutes.sum()
        kpis(part, ("Minutos de llamada", f"{total_min:,.0f}"))
        with st.container(border=True):
            st.markdown("**Gasto diario por agente**")
            st.plotly_chart(daily_by_resource(part), width="stretch", key="el_daily")
        c1, c2 = st.columns([3, 2])
        with c1.container(border=True):
            st.markdown("**Por agente**")
            llm = part[part["model"] == "convai_llm"].groupby("recurso")["cost"].sum().rename("LLM")
            extra = pd.concat([minutes.rename("Minutos"), llm], axis=1).reset_index(names="recurso")
            table = resource_table(part, extra)
            table[f"{currency}/min"] = table[f"Gasto ({currency})"] / table["Minutos"]
            st.dataframe(table, hide_index=True, width="stretch",
                         column_config={f"Gasto ({currency})": MONEY, "LLM": MONEY,
                                        "Minutos": st.column_config.NumberColumn(format="%,.0f"),
                                        f"{currency}/min": st.column_config.NumberColumn(format="$%.3f"),
                                        "%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)})
        with c2.container(border=True):
            st.markdown("**Llamada vs. LLM**")
            split = part.assign(componente=part["model"].map({"convai_voice": "Llamada (voz)", "convai_llm": "LLM"})
                                .fillna("Otros")).groupby("componente")["cost"].sum().reset_index()
            fig = px.pie(split, names="componente", values="cost", hole=0.55,
                         color="componente", color_discrete_map={"Llamada (voz)": CATEGORICAL_LIGHT[0],
                                                                 "LLM": CATEGORICAL_LIGHT[1], "Otros": NEUTRAL["light"]})
            fig.update_traces(textinfo="percent+label",
                              hovertemplate=f"%{{label}}<br><b>$%{{value:,.2f}} {currency}</b><extra></extra>")
            st.plotly_chart(style_fig(fig, height=300).update_layout(showlegend=False), width="stretch", key="el_pie")
        st.caption("Estimado: minutos de cada agente × costo por minuto medido en una muestra diaria de conversaciones "
                   "(coincide con el panel de ElevenLabs a menos de 1 %). El recargo de Voice Library "
                   "(\"Unknown Resource\") aparece en $0 hasta validarlo con factura.")

# --- Deepgram -------------------------------------------------------------------------------------------------
with tab_dg:
    part = df[df["provider"] == "deepgram"]
    if part.empty:
        st.info("Sin gasto de Deepgram en el periodo.")
    else:
        hours = seconds[seconds["provider"] == "deepgram"].groupby("recurso")["secs"].sum() / 3600
        kpis(part, ("Horas transcritas", f"{hours.sum():,.1f}"))
        with st.container(border=True):
            st.markdown("**Gasto diario por API key**")
            st.plotly_chart(daily_by_resource(part), width="stretch", key="dg_daily")
        with st.container(border=True):
            st.markdown("**Por API key**")
            table = resource_table(part, hours.rename("Horas").rename_axis("recurso").reset_index())
            st.dataframe(table, hide_index=True, width="stretch",
                         column_config={f"Gasto ({currency})": MONEY,
                                        "Horas": st.column_config.NumberColumn(format="%,.1f"),
                                        "%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)})
        st.caption("Horas exactas de la API de Deepgram × tarifa cargada en `rates` "
                   "(Deepgram no da el monto por key).")
