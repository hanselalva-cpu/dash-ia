from datetime import date, datetime, timezone
from uuid import uuid4

from models.schemas import Campaign
from pages.common import preset_range
from services.chart_theme import CATEGORICAL_LIGHT, NEUTRAL, OTHERS, UNASSIGNED, campaign_color_map, display_name


def _c(name, day):
    return Campaign(id=uuid4(), name=name, created_at=datetime(2026, 1, day, tzinfo=timezone.utc))


def test_color_follows_creation_order_not_name_or_rank():
    colors = campaign_color_map([_c("Zeta", 1), _c("Alfa", 2)])
    assert colors["Zeta"] == CATEGORICAL_LIGHT[0] and colors["Alfa"] == CATEGORICAL_LIGHT[1]
    # agregar una campaña nueva no repinta las existentes
    colors2 = campaign_color_map([_c("Zeta", 1), _c("Alfa", 2), _c("Beta", 3)])
    assert colors2["Zeta"] == colors["Zeta"] and colors2["Alfa"] == colors["Alfa"]


def test_ninth_campaign_folds_into_others_never_cycles():
    camps = [_c(f"C{i}", i + 1) for i in range(9)]
    colors = campaign_color_map(camps)
    assert colors["C8"] == NEUTRAL["light"]
    assert display_name("C8", colors) == OTHERS
    assert display_name("C0", colors) == "C0"
    assert display_name(UNASSIGNED, colors) == UNASSIGNED


def test_presets():
    today = date(2026, 10, 12)
    assert preset_range("Mes actual", today) == (date(2026, 10, 1), today)
    assert preset_range("Mes anterior", today) == (date(2026, 9, 1), date(2026, 9, 30))
    assert preset_range("Mes anterior", date(2026, 1, 5)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert preset_range("Últimos 30 días", today) == (date(2026, 9, 13), today)
