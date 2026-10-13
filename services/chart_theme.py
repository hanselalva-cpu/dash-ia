"""Paleta y colores estables por campaña (paleta categórica de referencia del skill dataviz, validada CVD)."""

from models.schemas import Campaign

# Orden fijo de slots, modo claro / modo oscuro. Nunca se cicla: campañas más allá del slot 8 → "Otras".
CATEGORICAL_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
CATEGORICAL_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
NEUTRAL = {"light": "#a3a29c", "dark": "#6b6a64"}  # "Sin campaña" / "Otras"

# Estado del presupuesto: colores reservados, siempre acompañados de icono + texto.
STATUS = {
    "ok": ("🟢", "En presupuesto", "#0ca30c"),
    "warning": ("🟠", "Cerca del tope", "#fab219"),
    "exceeded": ("🔴", "Tope alcanzado", "#d03b3b"),
    "no_budget": ("⚪", "Sin tope", "#a3a29c"),
}

UNASSIGNED = "Sin campaña"
OTHERS = "Otras campañas"


def campaign_color_map(campaigns: list[Campaign], mode: str = "light") -> dict[str, str]:
    """Color por nombre de campaña según su orden de creación: el color sigue a la entidad, no al ranking,
    así que filtrar o reordenar no repinta. Las que exceden los 8 slots comparten el neutro de "Otras"."""
    palette = CATEGORICAL_DARK if mode == "dark" else CATEGORICAL_LIGHT
    ordered = sorted(campaigns, key=lambda c: (c.created_at is None, c.created_at or 0, c.name))
    colors = {c.name: palette[i] if i < len(palette) else NEUTRAL[mode] for i, c in enumerate(ordered)}
    colors[UNASSIGNED] = NEUTRAL[mode]
    colors[OTHERS] = NEUTRAL[mode]
    return colors


def display_name(name: str, colors: dict[str, str]) -> str:
    """Campañas sin slot propio (más allá del 8º) se agrupan como "Otras campañas"."""
    if name == UNASSIGNED:
        return name
    return name if colors.get(name) not in (None, *NEUTRAL.values()) else OTHERS
