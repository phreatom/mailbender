from pydantic import SecretStr


def test_production_app_wires_factories_and_token(monkeypatch):
    import mailbender.api.bootstrap as bs

    class FakeCfg:
        database_url = "postgresql+psycopg://u:p@localhost/db"
        api_token = SecretStr("tok")

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

    monkeypatch.setattr(bs, "load_config", lambda: FakeCfg())
    monkeypatch.setattr(bs, "make_engine", lambda url: object())

    app = bs.production_app()
    assert app.state.api_token == ""
