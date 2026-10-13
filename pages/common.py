"""Utilidades compartidas por las páginas (no es una página: app.py usa st.navigation explícito)."""

import os
from datetime import date, datetime, time, timedelta

import streamlit as st

from config.settings import get_settings
from repositories import Repositories, get_repositories

PRESETS = ["Mes actual", "Mes anterior", "Últimos 30 días", "Año actual"]


@st.cache_resource
def _repos(config_fingerprint: str) -> Repositories:
    return get_repositories()


def repos() -> Repositories:
    """Repositorios cacheados por huella de configuración: editar Secrets no deja la app en modo viejo."""
    from config.settings import config_fingerprint

    return _repos(config_fingerprint())


def demo_banner() -> None:
    if not repos().demo:
        return
    from config.settings import streamlit_secrets

    found = sorted(streamlit_secrets())
    expected = ["DEMO_MODE", "SUPABASE_URL", "SUPABASE_SECRET_KEY", "DEFAULT_DISPLAY_CURRENCY", "USD_MXN_RATE"]
    missing = [k for k in expected if k not in found and k not in os.environ]
    lines = ["Modo demo: datos de ejemplo. Para usar Supabase define `DEMO_MODE = \"false\"` en .env (local) "
             "o en **Secrets** (Streamlit Cloud).",
             f"Valor de `DEMO_MODE` que está usando la app: `{os.environ.get('DEMO_MODE', '(no definido)')}`"]
    if missing:
        lines.append("No encontradas: " + ", ".join(f"`{k}`" for k in missing))
    lines.append("Claves leídas de Secrets: " + ", ".join(f"`{k}`" for k in found) if found
                 else "No se leyó ninguna clave de Secrets.")
    st.info("\n\n".join(lines))


def money(amount_usd: float, decimals: int = 2) -> str:
    """Formatea un monto en USD convertido a la moneda de visualización."""
    s = get_settings()
    return f"${amount_usd * s.display_rate:,.{decimals}f} {s.default_display_currency}"


def theme_mode() -> str:
    try:
        return st.context.theme.type or "light"
    except AttributeError:
        return "light"


def load_usage(start: datetime, end: datetime):
    from services.campaign_service import attribute_campaigns
    from services.usage_service import to_dataframe

    events = attribute_campaigns(repos().usage.list(start, end), repos().resources.list())
    df = to_dataframe(events, get_settings().display_rate)
    df["campaign"] = df["campaign_id"].map(campaign_names()).fillna("Sin campaña")
    return df


def today_local() -> date:
    return datetime.now(get_settings().tz).date()


def preset_range(preset: str, today: date) -> tuple[date, date]:
    first = today.replace(day=1)
    if preset == "Mes anterior":
        last_prev = first - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    if preset == "Últimos 30 días":
        return today - timedelta(days=29), today
    if preset == "Año actual":
        return today.replace(month=1, day=1), today
    return first, today  # Mes actual


def period_picker(key: str = "period") -> tuple[datetime, datetime]:
    """Dos calendarios (Desde / Hasta) + accesos rápidos. Por defecto el mes en curso.
    Devuelve [inicio, fin) en APP_TIMEZONE."""
    tz = get_settings().tz
    today = today_local()
    k_from, k_to, k_preset = f"{key}_from", f"{key}_to", f"{key}_preset"
    if k_from not in st.session_state:
        st.session_state[k_from], st.session_state[k_to] = preset_range("Mes actual", today)
        st.session_state[k_preset] = "Mes actual"

    def apply_preset():
        if st.session_state[k_preset]:
            st.session_state[k_from], st.session_state[k_to] = preset_range(st.session_state[k_preset], today)

    def mark_custom():
        st.session_state[k_preset] = None

    with st.container(border=True):
        c1, c2, c3 = st.columns([1, 1, 2.4], vertical_alignment="bottom")
        c1.date_input("📅 Desde", key=k_from, max_value=today, format="DD/MM/YYYY", on_change=mark_custom)
        c2.date_input("📅 Hasta", key=k_to, max_value=today, format="DD/MM/YYYY", on_change=mark_custom)
        c3.segmented_control("Periodo rápido", PRESETS, key=k_preset, on_change=apply_preset)

    start, end = st.session_state[k_from], st.session_state[k_to]
    if start > end:
        st.error("La fecha **Desde** no puede ser posterior a **Hasta**.")
        st.stop()
    return (
        datetime.combine(start, time.min, tzinfo=tz),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz),
    )


def style_fig(fig, height: int = 380):
    """Estilo común: ejes y rejilla discretos, barras con extremos redondeados y separación, leyenda arriba."""
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        barcornerradius=4,
        bargap=0.25,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        hoverlabel=dict(font_size=13),
        xaxis=dict(showgrid=False, title_text=""),
        yaxis=dict(gridcolor="rgba(128,128,128,0.15)", zeroline=False, title_text=""),
    )
    fig.update_traces(marker_line_width=0)
    return fig


def campaign_names() -> dict[str, str]:
    return {str(c.id): c.name for c in repos().campaigns.list()}
