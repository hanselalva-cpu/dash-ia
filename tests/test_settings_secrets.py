"""La configuración debe seguir a los Secrets de Streamlit Cloud aunque se editen con la app en marcha."""

import config.settings as cfg


def test_settings_follow_secrets_changes(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # sin .env
    for key in ["DEMO_MODE", "DEFAULT_DISPLAY_CURRENCY", "USD_MXN_RATE"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(cfg, "_FROM_SECRETS", set())
    monkeypatch.setattr(cfg, "_cached", None)

    secrets = {}
    monkeypatch.setattr(cfg, "streamlit_secrets", lambda: dict(secrets))
    first = cfg.get_settings()
    assert first.demo_mode is True and first.default_display_currency == "USD"
    fp1 = cfg.config_fingerprint()

    # Se guardan Secrets en Streamlit Cloud sin reiniciar el proceso
    secrets.update({"DEMO_MODE": "false", "DEFAULT_DISPLAY_CURRENCY": "MXN", "USD_MXN_RATE": "18.5"})
    second = cfg.get_settings()
    assert second.demo_mode is False and second.default_display_currency == "MXN"
    assert cfg.config_fingerprint() != fp1

    # Y si se vuelven a cambiar, también se actualiza (las variables puestas desde secrets no quedan fijas)
    secrets["DEMO_MODE"] = "true"
    assert cfg.get_settings().demo_mode is True


def test_real_env_vars_win_over_secrets(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEFAULT_DISPLAY_CURRENCY", "USD")
    monkeypatch.setattr(cfg, "_FROM_SECRETS", set())
    monkeypatch.setattr(cfg, "_cached", None)
    monkeypatch.setattr(cfg, "streamlit_secrets", lambda: {"DEFAULT_DISPLAY_CURRENCY": "MXN", "USD_MXN_RATE": "18"})
    assert cfg.get_settings().default_display_currency == "USD"


def test_keys_are_stripped(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "_FROM_SECRETS", set())
    monkeypatch.setattr(cfg, "_cached", None)
    monkeypatch.setattr(cfg, "streamlit_secrets", lambda: {
        "SUPABASE_URL": "https://x.supabase.co/", "SUPABASE_SECRET_KEY": '  "sb_secret_abc"\n'})
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    s = cfg.get_settings()
    assert s.supabase_key == "sb_secret_abc" and s.supabase_url == "https://x.supabase.co"
