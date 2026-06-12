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


def test_priorities_renders_human(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))

    def handler(request):
        assert request.url.path == "/priorities"
        return httpx.Response(200, json=[{"uid": "1", "priority": "high", "category": "X"}])

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["priorities"])
    assert result.exit_code == 0
    assert "high" in result.stdout


def test_priorities_json(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))
    rows = [{"uid": "1", "priority": "high", "category": "X"}]

    def handler(request):
        return httpx.Response(200, json=rows)

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["--json", "priorities"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == rows


def test_run_sends_type(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok", "run_type": "style"})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["run", "--type", "style"])
    assert result.exit_code == 0
    assert seen["body"] == {"run_type": "style"}


def test_categories_add(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"name": "Rechnung", "description": ""})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["categories", "add", "Rechnung"])
    assert result.exit_code == 0
    assert seen["method"] == "POST" and seen["path"] == "/categories"


def test_chat_renders(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))

    def handler(request):
        return httpx.Response(200, json={"text": "Sarah approved", "sources": []})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["chat", "what did sarah say?"])
    assert result.exit_code == 0
    assert "Sarah approved" in result.stdout


def test_unconfigured_api_command_exits_nonzero(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url=None, token=None))
    result = runner.invoke(app, ["priorities"])
    assert result.exit_code != 0
    assert "login" in (result.stdout + result.stderr).lower()


def test_mappings_remove_missing_exits_nonzero(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))

    def handler(request):
        return httpx.Response(200, json={"removed": False})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["mappings", "remove", "Nope"])
    assert result.exit_code != 0
