from pydantic import SecretStr


def test_production_app_wires_factories_and_token(monkeypatch):
    import mailbender.api.bootstrap as bs

    class FakeCfg:
        database_url = "postgresql+psycopg://u:p@localhost/db"
        api_token = SecretStr("tok")
        web_password = None
        secret_key = None
        schedule_minutes = 15

    monkeypatch.setattr(bs, "load_config", lambda: FakeCfg())
    monkeypatch.setattr(bs, "make_engine", lambda url: object())

    app = bs.production_app()
    assert app.state.api_token == "tok"
    assert app.state.repo_factory is not None
    assert app.state.runner_factory is not None
    assert app.state.chat_factory is not None


def test_production_app_empty_token_when_unset(monkeypatch):
    import mailbender.api.bootstrap as bs

    class FakeCfg:
        database_url = "postgresql+psycopg://u:p@localhost/db"
        api_token = None
        web_password = None
        secret_key = None
        schedule_minutes = 15

    monkeypatch.setattr(bs, "load_config", lambda: FakeCfg())
    monkeypatch.setattr(bs, "make_engine", lambda url: object())

    app = bs.production_app()
    assert app.state.api_token == ""


def test_production_app_mounts_web_and_builds_security(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    monkeypatch.setenv("MAILBENDER_WEB_PASSWORD", "pw")
    monkeypatch.setenv("MAILBENDER_SECRET_KEY", "k" * 32)
    import mailbender.api.bootstrap as b
    monkeypatch.setattr(b, "make_engine", lambda url: object())
    app = b.production_app()
    assert app.state.web_security.login_enabled is True
    assert any(getattr(r, "path", None) == "/login" for r in app.routes)


def test_production_app_warns_without_secret_key(monkeypatch, recwarn):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    monkeypatch.delenv("MAILBENDER_SECRET_KEY", raising=False)
    import mailbender.api.bootstrap as b
    monkeypatch.setattr(b, "make_engine", lambda url: object())
    app = b.production_app()
    assert app.state.web_security is not None
    assert any("SECRET_KEY" in str(w.message) for w in recwarn.list)


def test_production_app_exposes_schedule_minutes(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    monkeypatch.setenv("MAILBENDER_SCHEDULE_MINUTES", "30")
    import mailbender.api.bootstrap as b
    monkeypatch.setattr(b, "make_engine", lambda url: object())
    app = b.production_app()
    assert app.state.schedule_minutes == 30
