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

# Gasto del mes en curso por recurso (ElevenLabs separado en llamada, LLM y recargo de voz)
today = today_local()
month_start = datetime.combine(today.replace(day=1), time.min, tzinfo=settings.tz)
COMPONENT_COL = {"voice": "Llamada", "llm": "LLM", "voice_library": "Recargo voz"}
spent: dict[tuple[str, str], float] = {}
parts: dict[tuple[str, str], dict[str, float]] = {}
voice_of: dict[tuple[str, str], str] = {}
for event in repos().usage.list(month_start, datetime.now(settings.tz)):
    key = resource_key_of(event)
    if key is None:
        continue
    rk, cost = (str(event.provider), key), float(event.cost_usd or 0)
    spent[rk] = spent.get(rk, 0.0) + cost
    col = COMPONENT_COL.get(event.metadata.get("component"))
    if col:
        parts.setdefault(rk, {})[col] = parts.setdefault(rk, {}).get(col, 0.0) + cost
    if event.metadata.get("voice_name"):
        voice_of[rk] = event.metadata["voice_name"]

rate = settings.display_rate
rows = []
for r in resources:
    rk = (str(r.provider), r.resource_key)
    comp = parts.get(rk, {})
    is_el = str(r.provider) == "elevenlabs"
    rows.append({
        "Proveedor": PROVIDER_LABEL.get(str(r.provider), str(r.provider)),
        "Tipo": "Agente" if r.kind == "agent" else "API key",
        "Nombre": r.name,
        "Voz": voice_of.get(rk) if is_el else None,
        "Proyecto": r.group_name,
        "Campaña": campaign_names.get(r.campaign_id, "— Sin campaña"),
        "Llamada": comp.get("Llamada", 0.0) * rate if is_el else None,
        "LLM": comp.get("LLM", 0.0) * rate if is_el else None,
        "Recargo voz": comp.get("Recargo voz", 0.0) * rate if is_el else None,
        f"Gasto del mes ({currency})": spent.get(rk, 0.0) * rate,
        "Estado": "Activo" if r.active else "Inactivo",
    })
df = pd.DataFrame(rows)

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
show_inactive = f2.toggle("Incluir inactivos (sin gasto en 15 días)", value=False)
search = f3.text_input("Buscar", placeholder="Nombre, proyecto o campaña")

view = df
if providers:
    view = view[view["Proveedor"].isin(providers)]
if only_unassigned:
    view = view[view["Campaña"] == "— Sin campaña"]
if only_spend:
    view = view[view[f"Gasto del mes ({currency})"] > 0]
if not show_inactive:
    view = view[view["Estado"] == "Activo"]
if search:
    mask = view[["Nombre", "Proyecto", "Campaña"]].fillna("").apply(
        lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)
    view = view[mask]

money_col = st.column_config.NumberColumn(format="$%,.2f")
st.dataframe(
    view.sort_values(f"Gasto del mes ({currency})", ascending=False),
    hide_index=True,
    width="stretch",
    column_config={f"Gasto del mes ({currency})": money_col, "Llamada": money_col, "LLM": money_col,
                   "Recargo voz": st.column_config.NumberColumn(
                       format="$%,.2f", help="Cargo de ElevenLabs por usar voces de la Voice Library")},
)
st.caption(f"{len(view)} de {len(df)} recursos · Llamada, LLM y Recargo voz aplican a agentes de ElevenLabs; "
           "su suma es el gasto del mes.")

# --- Voces de ElevenLabs --------------------------------------------------------------------------------------
el = df[(df["Proveedor"] == "ElevenLabs") & df["Voz"].notna()]
if not el.empty:
    st.subheader("Voces de ElevenLabs")
    voices = (el.groupby("Voz").agg(Agentes=("Nombre", lambda n: ", ".join(sorted(n))),
                                    **{"Recargo voz": ("Recargo voz", "sum"),
                                       f"Gasto total de sus agentes ({currency})": (f"Gasto del mes ({currency})", "sum")})
              .reset_index().sort_values("Recargo voz", ascending=False))
    voices["Voice Library"] = voices["Recargo voz"].gt(0).map({True: "Sí (cobra recargo)", False: "No"})
    st.dataframe(voices[["Voz", "Voice Library", "Recargo voz", f"Gasto total de sus agentes ({currency})", "Agentes"]],
                 hide_index=True, width="stretch",
                 column_config={"Recargo voz": money_col, f"Gasto total de sus agentes ({currency})": money_col})
    st.caption("Mes en curso. La voz es la configurada hoy en cada agente.")
