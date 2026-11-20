"""Catálogo de campañas y asignación de recursos (API keys / agentes) de cada proveedor."""

from collections import Counter
from datetime import datetime, timedelta

import streamlit as st

from config.settings import get_settings
from models.schemas import Campaign, Provider
from pages.common import demo_banner, repos

PROVIDER_SECTIONS = [
    (Provider.OPENAI, "API keys de OpenAI"),
    (Provider.DEEPGRAM, "API keys de Deepgram"),
    (Provider.ELEVENLABS, "Agentes de ElevenLabs"),
]
STATUSES = ["active", "paused", "archived"]
UNKNOWN = "Unknown Resource"

st.title("Campañas")
demo_banner()
read_only = repos().demo

campaigns = repos().campaigns.list()
resources = repos().resources.list()
by_id = {r.id: r for r in resources}
assigned_count = Counter(r.campaign_id for r in resources if r.campaign_id)
alerts = {a.campaign_id: a for a in repos().alerts.list()}

# Voz de cada agente de ElevenLabs (de los últimos 60 días de uso) y si cobra recargo de Voice Library.
settings = get_settings()
voices: dict[str, tuple[str, bool]] = {}
for e in repos().usage.list(datetime.now(settings.tz) - timedelta(days=60), datetime.now(settings.tz)):
    if str(e.provider) == "elevenlabs" and e.metadata.get("voice_name"):
        library = bool(e.metadata.get("voice_library")) or e.metadata.get("component") == "voice_library"
        prev = voices.get(e.metadata["agent_name"], (None, False))
        voices[e.metadata["agent_name"]] = (e.metadata["voice_name"], prev[1] or library)

# --- Catálogo ---------------------------------------------------------------------------------------------
st.dataframe(
    [
        {
            "Campaña": c.name,
            "Cliente": c.client,
            "Tope mensual": (f"${alerts[c.id].limit_amount:,.2f} {alerts[c.id].currency}"
                             if c.id in alerts else "—"),
            "Estado": c.status,
            "Recursos": assigned_count.get(c.id, 0),
        }
        for c in campaigns
    ],
    width="stretch",
    hide_index=True,
)
unassigned = sum(1 for r in resources if not r.campaign_id and r.active)
if resources:
    st.caption(f"{len(resources)} recursos en catálogo · {unassigned} activos sin campaña. "
               "El catálogo se actualiza con la sincronización diaria.")
else:
    st.warning("Catálogo de recursos vacío: ejecuta la migración 006 y una sincronización (scripts\\sync_all.ps1).")

# --- Nueva campaña ----------------------------------------------------------------------------------------
with st.expander("➕ Nueva campaña"):
    with st.form("new_campaign", clear_on_submit=True):
        name = st.text_input("Nombre *")
        client = st.text_input("Cliente")
        if st.form_submit_button("Crear", disabled=read_only):
            if not name.strip():
                st.error("El nombre es obligatorio")
            elif name.strip().lower() in {c.name.lower() for c in campaigns}:
                st.error("Ya existe una campaña con ese nombre")
            else:
                repos().campaigns.create(Campaign(name=name.strip(), client=client.strip() or None))
                st.toast(f"Campaña '{name.strip()}' creada. Define su tope en Alertas.", icon="✅")
                st.rerun()

# --- Editar y asignar recursos ----------------------------------------------------------------------------
if not campaigns:
    st.stop()

st.subheader("Editar campaña y asignar recursos")
campaign = st.selectbox("Campaña", campaigns, format_func=lambda c: c.name)


def resource_label(rid) -> str:
    r = by_id[rid]
    if r.provider == Provider.ELEVENLABS and r.resource_key == UNKNOWN:
        return "Recargo de voz sin agente (Voice Library)"
    extra = f" · {r.group_name}" if r.group_name else ""
    if r.provider == Provider.ELEVENLABS and r.name in voices:
        voice, library = voices[r.name]
        extra += f" · 🎙️ {voice}" + (" (cobra recargo)" if library else "")
    return f"{r.name}{extra}{'' if r.active else ' (inactivo)'}"


with st.form(f"edit_{campaign.id}"):
    c1, c2 = st.columns(2)
    name = c1.text_input("Nombre", campaign.name)
    client = c2.text_input("Cliente", campaign.client or "")
    status = st.selectbox("Estado", STATUSES, index=STATUSES.index(campaign.status))

    st.markdown("**Recursos de la campaña.** Cada recurso pertenece a una sola campaña; "
                "aquí solo aparecen los libres y los ya asignados a esta.")
    show_inactive = st.toggle("Mostrar recursos inactivos (sin gasto en 15 días)", value=False)
    selected = set()
    for provider, label in PROVIDER_SECTIONS:
        options = [r.id for r in resources
                   if r.provider == provider and r.campaign_id in (None, campaign.id)
                   and (r.active or show_inactive or r.campaign_id == campaign.id)]
        current = [r.id for r in resources if r.provider == provider and r.campaign_id == campaign.id]
        taken = sum(1 for r in resources if r.provider == provider and r.campaign_id not in (None, campaign.id))
        picked = st.multiselect(label, options, default=current, format_func=resource_label,
                                help=f"{taken} asignados a otras campañas (no se muestran)" if taken else None)
        if provider == Provider.ELEVENLABS:
            st.caption("🎙️ La voz de cada agente va con el agente: su costo de llamada, LLM y **recargo de voz** "
                       "(Voice Library) se asignan a la campaña del agente, no por separado. \"Recargo de voz sin "
                       "agente\" son días con recargo sin ningún agente de voz de biblioteca activo.")
        selected.update(picked)

    if st.form_submit_button("Guardar", type="primary", disabled=read_only):
        if not name.strip():
            st.error("El nombre es obligatorio")
        else:
            repos().campaigns.update(campaign.id, {
                "name": name.strip(),
                "client": client.strip() or None,
                "status": status,
            })
            repos().resources.assign(campaign.id, selected)
            st.toast("Guardado. El costo histórico de estos recursos ya se atribuye a la campaña.", icon="✅")
            st.rerun()

# --- Recursos asignados (vista rápida) --------------------------------------------------------------------
mine = [r for r in resources if r.campaign_id == campaign.id]
if mine:
    st.dataframe(
        [{"Proveedor": str(r.provider), "Tipo": "Agente" if r.kind == "agent" else "API key",
          "Nombre": resource_label(r.id), "Voz": voices.get(r.name, (None,))[0],
          "Grupo/proyecto": r.group_name} for r in mine],
        width="stretch", hide_index=True,
    )
