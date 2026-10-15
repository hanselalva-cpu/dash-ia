"""Comparativo de costos entre dos campañas en el mismo periodo."""

import pandas as pd
import plotly.express as px
import streamlit as st

from config.settings import get_settings
from pages.common import demo_banner, load_usage, period_picker, repos, style_fig, theme_mode
from services.chart_theme import CATEGORICAL_DARK, CATEGORICAL_LIGHT, NEUTRAL, UNASSIGNED, campaign_color_map

settings = get_settings()
currency = settings.default_display_currency
PROVIDER_LABEL = {"openai": "OpenAI", "deepgram": "Deepgram", "elevenlabs": "ElevenLabs", "anthropic": "Anthropic"}

st.title("Comparativo de campañas")
demo_banner()

start, end = period_picker(key="cmp")
df = load_usage(start, end)
if df.empty:
    st.info("Sin gasto en el periodo seleccionado.")
    st.stop()

# --- Selección de las dos campañas (por defecto, las dos de mayor gasto en el periodo) ----------------------
ranking = df.groupby("campaign")["cost"].sum().sort_values(ascending=False)
options = list(ranking.index)
if len(options) < 2:
    st.info("Se necesitan al menos dos campañas con gasto en el periodo para comparar.")
    st.stop()
c1, c2 = st.columns(2)
a = c1.selectbox("Campaña A", options, index=0, key="cmp_a")
b = c2.selectbox("Campaña B", [o for o in options if o != a], index=0, key="cmp_b")

# Colores: los de cada campaña; si coinciden (neutro / más de 8 campañas), dos slots distintos de la paleta.
mode = theme_mode()
colors = campaign_color_map(repos().campaigns.list(), mode)
col_a, col_b = colors.get(a, NEUTRAL[mode]), colors.get(b, NEUTRAL[mode])
if col_a == col_b or a == UNASSIGNED or b == UNASSIGNED:
    palette = CATEGORICAL_DARK if mode == "dark" else CATEGORICAL_LIGHT
    col_a, col_b = palette[0], palette[1]
pair_colors = {a: col_a, b: col_b}

sub = df[df["campaign"].isin([a, b])].copy()
sub["día"] = sub["occurred_at"].dt.tz_convert(settings.app_timezone).dt.date
sub["proveedor"] = sub["provider"].map(PROVIDER_LABEL).fillna(sub["provider"])
days = max((end - start).days, 1)
tot_a = sub.loc[sub["campaign"] == a, "cost"].sum()
tot_b = sub.loc[sub["campaign"] == b, "cost"].sum()


def fmt(v: float) -> str:
    return f"{'-' if v < 0 else ''}${abs(v):,.2f} {currency}"


# --- Indicadores lado a lado ---------------------------------------------------------------------------------
k1, k2, k3 = st.columns(3)
with k1.container(border=True):
    st.markdown(f"**A · {a}**")
    st.metric("Gasto del periodo", fmt(tot_a))
    st.metric("Promedio diario", fmt(tot_a / days))
with k2.container(border=True):
    st.markdown(f"**B · {b}**")
    st.metric("Gasto del periodo", fmt(tot_b))
    st.metric("Promedio diario", fmt(tot_b / days))
with k3.container(border=True):
    st.markdown("**Diferencia (B − A)**")
    diff = tot_b - tot_a
    st.metric("En el periodo", fmt(diff),
              f"{diff / tot_a:+.1%} vs A" if tot_a else None, delta_color="inverse")
    bigger, smaller = (a, b) if tot_a >= tot_b else (b, a)
    ratio = max(tot_a, tot_b) / min(tot_a, tot_b) if min(tot_a, tot_b) else None
    st.caption(f"**{bigger}** gasta " + (f"**{ratio:,.1f}×** lo de {smaller}." if ratio else "y la otra no tiene gasto."))

# --- Evolución diaria ----------------------------------------------------------------------------------------
with st.container(border=True):
    st.markdown("**Gasto diario**")
    all_days = pd.date_range(start.date(), (end - pd.Timedelta(days=1)).date(), freq="D").date
    daily = (sub.groupby(["día", "campaign"])["cost"].sum()
             .unstack(fill_value=0).reindex(index=all_days, columns=[a, b], fill_value=0)
             .rename_axis("día").reset_index().melt(id_vars="día", var_name="campaña", value_name="cost"))
    fig = px.line(daily, x="día", y="cost", color="campaña", color_discrete_map=pair_colors, markers=True,
                  category_orders={"campaña": [a, b]})
    fig.update_traces(line_width=2, marker_size=8,
                      hovertemplate=f"%{{x|%d %b}}<br><b>$%{{y:,.2f}} {currency}</b><extra>%{{fullData.name}}</extra>")
    fig = style_fig(fig)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(type="date", tickformat="%d %b")
    st.plotly_chart(fig, width="stretch")

# --- Por proveedor -------------------------------------------------------------------------------------------
left, right = st.columns([3, 2])
by_prov = (sub.groupby(["proveedor", "campaign"])["cost"].sum().unstack(fill_value=0)
           .reindex(columns=[a, b], fill_value=0))
with left.container(border=True):
    st.markdown("**Gasto por proveedor**")
    long = by_prov.reset_index().melt(id_vars="proveedor", var_name="campaña", value_name="cost")
    fig = px.bar(long, x="proveedor", y="cost", color="campaña", barmode="group", color_discrete_map=pair_colors,
                 category_orders={"campaña": [a, b]},
                 text=long["cost"].map(lambda v: f"${v:,.0f}" if v else ""))
    fig.update_traces(textposition="outside", cliponaxis=False,
                      hovertemplate=f"%{{x}}<br><b>$%{{y:,.2f}} {currency}</b><extra>%{{fullData.name}}</extra>")
    st.plotly_chart(style_fig(fig, height=340), width="stretch")
with right.container(border=True):
    st.markdown("**Tabla por proveedor**")
    table = by_prov.copy()
    table["Diferencia (B − A)"] = table[b] - table[a]
    table.loc["Total"] = table.sum()
    money = st.column_config.NumberColumn(format="$%,.2f")
    st.dataframe(table.reset_index().rename(columns={"proveedor": "Proveedor", a: f"A · {a}", b: f"B · {b}"}),
                 hide_index=True, width="stretch",
                 column_config={f"A · {a}": money, f"B · {b}": money, "Diferencia (B − A)": money})

# --- Recursos que más gastan en cada campaña ---------------------------------------------------------------
with st.container(border=True):
    st.markdown("**Agentes / API keys que más gastan**")
    r1, r2 = st.columns(2)
    for col, name in ((r1, a), (r2, b)):
        part = sub[sub["campaign"] == name]
        res = (part.assign(recurso=part["agent"].fillna(part["model"]))
               .groupby(["proveedor", "recurso"])["cost"].sum().reset_index()
               .sort_values("cost", ascending=False))
        res = res[res["cost"] > 0.005]
        res["%"] = res["cost"] / res["cost"].sum() * 100 if len(res) else 0
        col.markdown(f"*{name}*")
        col.dataframe(res.rename(columns={"proveedor": "Proveedor", "recurso": "Agente / API key",
                                          "cost": f"Gasto ({currency})"}),
                      hide_index=True, width="stretch",
                      column_config={f"Gasto ({currency})": st.column_config.NumberColumn(format="$%,.2f"),
                                     "%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0,
                                                                         max_value=100)})
