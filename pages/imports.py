import streamlit as st

from pages.common import demo_banner, money, repos
from services.import_service import parse_usage_csv
from services.pricing_service import calculate_cost

st.title("Importar consumo")
demo_banner()
st.caption("Formato: examples/usage_template.csv. Reimportar con el mismo external_id no duplica.")

uploaded = st.file_uploader("CSV", type="csv")
if uploaded is None:
    st.stop()

result = parse_usage_csv(uploaded.getvalue().decode("utf-8-sig"))
if result.errors:
    st.error(f"{len(result.errors)} filas con error")
    st.dataframe([{"fila": r, "error": e} for r, e in result.errors], hide_index=True)

rates = repos().rates.list()
missing = 0
for event in result.events:
    breakdown = calculate_cost(event, rates)
    event.cost_usd = breakdown.total_usd
    missing += not breakdown.complete

st.success(f"{len(result.events)} filas válidas · costo {money(float(sum(e.cost_usd for e in result.events)), 4)}")
if missing:
    st.warning(f"{missing} filas sin tarifa para alguna unidad (costo parcial).")

if st.button("Guardar en Supabase", disabled=repos().demo or not result.events):
    saved = repos().usage.upsert_many(result.events)
    st.success(f"Guardadas {saved} filas")
