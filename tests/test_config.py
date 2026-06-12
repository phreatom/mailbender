import os
from mailbender.config import load_config


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "me@example.com")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "secret")
    monkeypatch.setenv("MAILBENDER_LLM_PROVIDER", "fake")
    cfg = load_config()
    assert cfg.database_url == "postgresql+psycopg://u:p@localhost/db"
    assert cfg.imap.host == "imap.example.com"
    assert cfg.imap.user == "me@example.com"
    assert cfg.imap.password.get_secret_value() == "secret"
    assert cfg.llm_provider == "fake"


def test_defaults(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    cfg = load_config()
    assert cfg.llm_provider == "openai"
    assert cfg.imap.port == 993
    assert cfg.schedule_minutes == 15


def test_schedule_interval_defaults(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    from mailbender.config import load_config
    cfg = load_config()
    assert cfg.schedule_minutes == 15
    assert cfg.feedback_minutes == 60
    assert cfg.style_minutes == 0  # 0 = manual-only


def test_schedule_intervals_from_env(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    monkeypatch.setenv("MAILBENDER_FEEDBACK_MINUTES", "30")
    monkeypatch.setenv("MAILBENDER_STYLE_MINUTES", "1440")
    from mailbender.config import load_config
    cfg = load_config()
    assert cfg.feedback_minutes == 30
    assert cfg.style_minutes == 1440


def test_api_token_from_env(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    monkeypatch.setenv("MAILBENDER_API_TOKEN", "secret-token")
    from mailbender.config import load_config
    cfg = load_config()
    assert cfg.api_token.get_secret_value() == "secret-token"


def test_api_token_defaults_none(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    from mailbender.config import load_config
    cfg = load_config()
    assert cfg.api_token is None


def test_web_fields_load_from_env(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("MAILBENDER_WEB_PASSWORD", "hunter2")
    monkeypatch.setenv("MAILBENDER_SECRET_KEY", "s3cret-key")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    from mailbender.config import load_config
    cfg = load_config()
    assert cfg.web_password.get_secret_value() == "hunter2"
    assert cfg.secret_key.get_secret_value() == "s3cret-key"


def test_web_fields_default_to_none(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    monkeypatch.delenv("MAILBENDER_WEB_PASSWORD", raising=False)
    monkeypatch.delenv("MAILBENDER_SECRET_KEY", raising=False)
    from mailbender.config import load_config
    cfg = load_config()
    assert cfg.web_password is None
    assert cfg.secret_key is None
