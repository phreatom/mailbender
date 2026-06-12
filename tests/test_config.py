import os
from mailagent.config import load_config


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("MAILAGENT_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILAGENT_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("MAILAGENT_IMAP_USER", "me@example.com")
    monkeypatch.setenv("MAILAGENT_IMAP_PASSWORD", "secret")
    monkeypatch.setenv("MAILAGENT_LLM_PROVIDER", "fake")
    cfg = load_config()
    assert cfg.database_url == "postgresql+psycopg://u:p@localhost/db"
    assert cfg.imap.host == "imap.example.com"
    assert cfg.imap.user == "me@example.com"
    assert cfg.imap.password.get_secret_value() == "secret"
    assert cfg.llm_provider == "fake"


def test_defaults(monkeypatch):
    monkeypatch.setenv("MAILAGENT_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILAGENT_IMAP_HOST", "h")
    monkeypatch.setenv("MAILAGENT_IMAP_USER", "u")
    monkeypatch.setenv("MAILAGENT_IMAP_PASSWORD", "p")
    cfg = load_config()
    assert cfg.llm_provider == "openai"
    assert cfg.imap.port == 993
    assert cfg.schedule_minutes == 15
