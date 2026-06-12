import json
import httpx
import pytest
from typer.testing import CliRunner
from mailbender.cli import main
from mailbender.cli.main import app
from mailbender.client.config import ClientConfig

runner = CliRunner()


def _patch_client(monkeypatch, handler):
    def factory(cfg):
        from mailbender.client.api import ApiClient
        return ApiClient(ClientConfig(url="http://api", token="tok"),
                         transport=httpx.MockTransport(handler))
    monkeypatch.setattr(main, "_client_factory", factory)


def test_version_is_local():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_status_reports_url_and_token_presence(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))

    def handler(request):
        return httpx.Response(200, json={"status": "ok"})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "http://api" in result.stdout
    assert "tok" not in result.stdout  # token value never printed


def test_login_writes_config_with_flags(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(main, "config_path", lambda: path)

    def handler(request):
        return httpx.Response(200, json={"status": "ok"})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(
        app, ["login", "--url", "http://api", "--token", "tok"])
    assert result.exit_code == 0
    assert path.exists()
    import tomllib
    data = tomllib.loads(path.read_text())
    assert data["url"] == "http://api" and data["token"] == "tok"


def test_logout_removes_config(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('url = "x"\ntoken = "y"\n')
    monkeypatch.setattr(main, "config_path", lambda: path)
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert not path.exists()
