"""Entrada Streamlit:  streamlit run app.py"""

import streamlit as st

from services.auth_service import require_login

st.set_page_config(page_title="Dash IA", page_icon="📊", layout="wide")

if require_login():
    nav = st.navigation(
        [
            st.Page("pages/dashboard.py", title="Dashboard", icon="📊", default=True),
            st.Page("pages/compare.py", title="Comparativo", icon="⚖️"),
            st.Page("pages/providers.py", title="Proveedores", icon="🧩"),
            st.Page("pages/payments.py", title="Pagos", icon="💰"),
            st.Page("pages/campaigns.py", title="Campañas", icon="🎯"),
            st.Page("pages/alerts.py", title="Alertas", icon="🚨"),
            st.Page("pages/api_keys.py", title="API keys y agentes", icon="🔑"),
            st.Page("pages/imports.py", title="Importar", icon="📥"),
        ]
    )
    nav.run()
