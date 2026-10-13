"""Login mínimo por contraseña compartida. TODO: reemplazar por Supabase Auth si hay varios usuarios."""

import hmac

import streamlit as st

from config.settings import get_settings


def require_login() -> bool:
    """Devuelve True si el usuario puede ver la app. Si no, dibuja el formulario de login."""
    password = get_settings().app_password.get_secret_value()
    if not password or st.session_state.get("authenticated"):
        return True

    st.title("Dash IA")
    entered = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        if hmac.compare_digest(entered, password):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Contraseña incorrecta")
    return False
