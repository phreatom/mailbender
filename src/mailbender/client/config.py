import os
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w


@dataclass
class ClientConfig:
    url: str | None = None
    token: str | None = None


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "mailbender" / "config.toml"


def _read_file(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def resolve_config(flag_url=None, flag_token=None, env=None, path=None) -> ClientConfig:
    env = os.environ if env is None else env
    path = config_path() if path is None else path
    data = _read_file(path)
    url = flag_url or env.get("MAILBENDER_API_URL") or data.get("url")
    token = flag_token or env.get("MAILBENDER_API_TOKEN") or data.get("token")
    return ClientConfig(url=url, token=token)


def save_config(cfg: ClientConfig, path=None) -> Path:
    path = config_path() if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        tomli_w.dump({"url": cfg.url or "", "token": cfg.token or ""}, f)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    return path


def delete_config(path=None) -> bool:
    path = config_path() if path is None else path
    if path.exists():
        path.unlink()
        return True
    return False
