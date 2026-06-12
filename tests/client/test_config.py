import stat
from pathlib import Path
from mailbender.client.config import (
    ClientConfig, resolve_config, save_config, delete_config,
)


def _write(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(body)
    return p


def test_resolution_order_flag_beats_env_beats_file(tmp_path):
    p = _write(tmp_path, 'url = "http://file"\ntoken = "file-tok"\n')
    env = {"MAILBENDER_API_URL": "http://env", "MAILBENDER_API_TOKEN": "env-tok"}
    c = resolve_config(env={}, path=p)
    assert c.url == "http://file" and c.token == "file-tok"
    c = resolve_config(env=env, path=p)
    assert c.url == "http://env" and c.token == "env-tok"
    c = resolve_config(flag_url="http://flag", flag_token="flag-tok", env=env, path=p)
    assert c.url == "http://flag" and c.token == "flag-tok"


def test_missing_everything_yields_none(tmp_path):
    c = resolve_config(env={}, path=tmp_path / "nope.toml")
    assert c.url is None and c.token is None


def test_save_writes_chmod_600_and_delete(tmp_path):
    p = tmp_path / "config.toml"
    save_config(ClientConfig(url="http://x", token="tok"), path=p)
    assert resolve_config(env={}, path=p) == ClientConfig(url="http://x", token="tok")
    mode = stat.S_IMODE(p.stat().st_mode)
    assert mode == 0o600
    assert delete_config(path=p) is True
    assert delete_config(path=p) is False
