"""Catálogo de campañas y asignación de recursos (API keys / agentes) de cada proveedor."""

from collections import Counter

import streamlit as st

from models.schemas import Campaign, Provider
from pages.common import demo_banner, repos

PROVIDER_SECTIONS = [
    (Provider.OPENAI, "API keys de OpenAI"),
    (Provider.DEEPGRAM, "API keys de Deepgram"),
    (Provider.ELEVENLABS, "Agentes de ElevenLabs"),
]
STATUSES = ["active", "paused", "archived"]

st.title("Campañas")
demo_banner()
read_only = repos().demo

campaigns = repos().campaigns.list()
resources = repos().resources.list()
by_id = {r.id: r for r in resources}
assigned_count = Counter(r.campaign_id for r in resources if r.campaign_id)
alerts = {a.campaign_id: a for a in repos().alerts.list()}

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
    extra = f" · {r.group_name}" if r.group_name else ""
    return f"{r.name}{extra}{'' if r.active else ' (inactivo)'}"


with st.form(f"edit_{campaign.id}"):
    c1, c2 = st.columns(2)
    name = c1.text_input("Nombre", campaign.name)
    client = c2.text_input("Cliente", campaign.client or "")
    status = st.selectbox("Estado", STATUSES, index=STATUSES.index(campaign.status))

    st.markdown("**Recursos de la campaña.** Cada recurso pertenece a una sola campaña; "
                "aquí solo aparecen los libres y los ya asignados a esta.")
    selected = set()
    for provider, label in PROVIDER_SECTIONS:
        options = [r.id for r in resources
                   if r.provider == provider and r.campaign_id in (None, campaign.id)]
        current = [r.id for r in resources if r.provider == provider and r.campaign_id == campaign.id]
        taken = sum(1 for r in resources if r.provider == provider and r.campaign_id not in (None, campaign.id))
        picked = st.multiselect(label, options, default=current, format_func=resource_label,
                                help=f"{taken} asignados a otras campañas (no se muestran)" if taken else None)
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
          "Nombre": r.name, "Grupo/proyecto": r.group_name} for r in mine],
        width="stretch", hide_index=True,
    )
