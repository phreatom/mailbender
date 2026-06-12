from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ImapConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILBENDER_IMAP_")
    host: str
    user: str
    password: SecretStr
    port: int = 993
    drafts_folder: str = "Drafts"
    sent_folder: str = "Sent"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILBENDER_")
    database_url: str
    llm_provider: str = "openai"
    llm_api_key: SecretStr | None = None
    schedule_minutes: int = 15
    feedback_minutes: int = 60
    style_minutes: int = 0
    imap: ImapConfig | None = None


def load_config() -> Config:
    cfg = Config()
    if cfg.imap is None:
        cfg.imap = ImapConfig()
    return cfg
