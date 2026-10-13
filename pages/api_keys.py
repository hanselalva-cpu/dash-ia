"""Catálogo de API keys y agentes de los proveedores, con su campaña y gasto del mes en curso."""

from datetime import datetime, time

import pandas as pd
import streamlit as st

from config.settings import get_settings
from pages.common import demo_banner, load_usage, money, repos, today_local
from services.campaign_service import resource_key_of

settings = get_settings()
currency = settings.default_display_currency
PROVIDER_LABEL = {"openai": "OpenAI", "deepgram": "Deepgram", "elevenlabs": "ElevenLabs", "anthropic": "Anthropic"}

st.title("API keys y agentes")
demo_banner()
st.caption("Se actualiza solo con la sincronización diaria (7:00 a. m.). La asignación a campañas se hace en "
           "la página **Campañas**.")

resources = repos().resources.list()
if not resources:
    st.info("Catálogo vacío: ejecuta la migración 006 y una sincronización (scripts\\sync_all.ps1).")
    st.stop()

campaign_names = {c.id: c.name for c in repos().campaigns.list()}

# Gasto del mes en curso por recurso
today = today_local()
month_start = datetime.combine(today.replace(day=1), time.min, tzinfo=settings.tz)
spent: dict[tuple[str, str], float] = {}
for event in repos().usage.list(month_start, datetime.now(settings.tz)):
    key = resource_key_of(event)
    if key is not None:
        spent[(str(event.provider), key)] = spent.get((str(event.provider), key), 0.0) + float(event.cost_usd or 0)

df = pd.DataFrame([
    {
        "Proveedor": PROVIDER_LABEL.get(str(r.provider), str(r.provider)),
        "Tipo": "Agente" if r.kind == "agent" else "API key",
        "Nombre": r.name,
        "Proyecto": r.group_name,
        "Campaña": campaign_names.get(r.campaign_id, "— Sin campaña"),
        f"Gasto del mes ({currency})": spent.get((str(r.provider), r.resource_key), 0.0) * settings.display_rate,
        "Estado": "Activo" if r.active else "Inactivo",
    }
    for r in resources
])

# --- Resumen ----------------------------------------------------------------------------------------------
unassigned = df[df["Campaña"] == "— Sin campaña"]
unassigned_spend = unassigned[f"Gasto del mes ({currency})"].sum() / settings.display_rate
with st.container(horizontal=True):
    for provider in ["OpenAI", "Deepgram", "ElevenLabs"]:
        n = int((df["Proveedor"] == provider).sum())
        if n:
            st.metric(provider, f"{n} {'agentes' if provider == 'ElevenLabs' else 'keys'}", border=True)
    st.metric("Sin campaña", f"{len(unassigned)} recursos", f"{money(unassigned_spend)} este mes",
              delta_color="off", border=True)

# --- Filtros ----------------------------------------------------------------------------------------------
f1, f2, f3 = st.columns([2, 2, 3], vertical_alignment="bottom")
providers = f1.pills("Proveedor", sorted(df["Proveedor"].unique()), selection_mode="multi")
only_unassigned = f2.toggle("Solo sin campaña")
only_spend = f2.toggle("Solo con gasto este mes", value=True)
search = f3.text_input("Buscar", placeholder="Nombre, proyecto o campaña")

view = df
if providers:
    view = view[view["Proveedor"].isin(providers)]
if only_unassigned:
    view = view[view["Campaña"] == "— Sin campaña"]
if only_spend:
    view = view[view[f"Gasto del mes ({currency})"] > 0]
if search:
    mask = view[["Nombre", "Proyecto", "Campaña"]].fillna("").apply(
        lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)
    view = view[mask]

st.dataframe(
    view.sort_values(f"Gasto del mes ({currency})", ascending=False),
    hide_index=True,
    width="stretch",
    column_config={f"Gasto del mes ({currency})": st.column_config.NumberColumn(format="$%,.2f")},
)
st.caption(f"{len(view)} de {len(df)} recursos")
