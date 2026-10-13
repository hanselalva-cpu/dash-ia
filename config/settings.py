import os
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_CURRENCIES = {"USD", "MXN"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: SecretStr = SecretStr("")

    app_timezone: str = "America/Mexico_City"
    default_display_currency: str = "USD"
    # Pesos por dólar. Solo afecta la visualización: tarifas, costos y presupuestos se guardan en USD.
    usd_mxn_rate: float | None = None
    # Sin .env → demo, para que el proyecto arranque recién clonado.
    demo_mode: bool = True

    app_password: SecretStr = SecretStr("")
    budget_warning_ratio: float = 0.8
    reconciliation_tolerance_pct: float = 0.02

    openai_api_key: SecretStr = SecretStr("")
    # Admin key (sk-admin-…) con api.usage.read: única forma de leer uso por API key de toda la organización.
    openai_admin_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    deepgram_api_key: SecretStr = SecretStr("")
    elevenlabs_api_key: SecretStr = SecretStr("")

    @field_validator("supabase_url")
    @classmethod
    def _base_url_only(cls, value: str) -> str:
        """supabase-py agrega /rest/v1 solo; si la URL ya lo trae, PostgREST responde PGRST125."""
        value = value.strip().rstrip("/")
        for suffix in ("/rest/v1", "/auth/v1", "/storage/v1"):
            value = value.removesuffix(suffix)
        return value

    @field_validator("app_timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)  # lanza si no existe
        return value

    @field_validator("default_display_currency")
    @classmethod
    def _supported_currency(cls, value: str) -> str:
        value = value.upper()
        if value not in SUPPORTED_CURRENCIES:
            raise ValueError(f"moneda {value} no soportada (usar {' o '.join(sorted(SUPPORTED_CURRENCIES))})")
        return value

    @field_validator("usd_mxn_rate", mode="before")
    @classmethod
    def _empty_rate_is_none(cls, value):
        return None if value in ("", None) else value

    @model_validator(mode="after")
    def _rate_required_for_mxn(self):
        if self.default_display_currency == "MXN" and (self.usd_mxn_rate is None or self.usd_mxn_rate <= 0):
            raise ValueError("DEFAULT_DISPLAY_CURRENCY=MXN requiere USD_MXN_RATE > 0 en .env (ej. USD_MXN_RATE=18.50)")
        return self

    @property
    def display_rate(self) -> float:
        """Multiplicador USD → moneda de visualización."""
        return self.usd_mxn_rate if self.default_display_currency == "MXN" else 1.0

    @property
    def openai_usage_key(self) -> str:
        """Admin key para la API de uso/costos; acepta también una sk-admin- puesta en OPENAI_API_KEY."""
        admin = self.openai_admin_key.get_secret_value()
        api = self.openai_api_key.get_secret_value()
        return admin or (api if api.startswith("sk-admin-") else "")

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @property
    def supabase_key(self) -> str:
        """Secret key si existe (server-side, salta RLS); si no, publishable."""
        return self.supabase_secret_key.get_secret_value() or self.supabase_publishable_key

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


def streamlit_secrets() -> dict[str, str]:
    """Claves de st.secrets (Streamlit Cloud → App settings → Secrets) aplanadas y en MAYÚSCULAS.
    Acepta claves de primer nivel o dentro de una sección ([general], [supabase], …). Sin secrets → {}."""
    try:
        import streamlit as st

        raw = st.secrets.to_dict()
    except Exception:  # sin secrets.toml, fuera de Streamlit, etc.
        return {}
    flat: dict[str, str] = {}
    for key, value in raw.items():
        items = value.items() if isinstance(value, dict) else [(key, value)]
        for k, v in items:
            if isinstance(v, (str, int, float, bool)):
                flat.setdefault(k.upper(), str(v).lower() if isinstance(v, bool) else str(v))
    return flat


def _apply_streamlit_secrets() -> None:
    """Variables de entorno ya definidas tienen prioridad; los secrets solo completan las que faltan."""
    for key, value in streamlit_secrets().items():
        os.environ.setdefault(key, value)


@lru_cache
def get_settings() -> Settings:
    _apply_streamlit_secrets()
    try:
        return Settings()
    except ValidationError as exc:
        # El mensaje por defecto de pydantic incluye los valores leídos (keys incluidas): no exponerlos.
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'config'}: {e['msg']}" for e in exc.errors(include_input=False)
        )
        raise RuntimeError(f"Configuración inválida (.env o Secrets) → {problems}") from None
