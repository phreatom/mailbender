import typer
from mailbender.scheduler.loop import run_loop

app = typer.Typer(help="Mailbender server-side operations")


@app.callback()
def _callback():
    """Mailbender server-side operations."""


def _load_config():
    from mailbender.config import load_config
    return load_config()


def _make_session(cfg):
    from mailbender.store.db import make_engine, make_session_factory
    engine = make_engine(cfg.database_url)
    return make_session_factory(engine)()


def _make_runner():
    from mailbender.imap.client import ImapClient
    from mailbender.llm.factory import make_provider
    from mailbender.scheduler.wiring import build_runner
    cfg = _load_config()
    session = _make_session(cfg)
    imap = ImapClient(
        host=cfg.imap.host, port=cfg.imap.port, user=cfg.imap.user,
        password=cfg.imap.password.get_secret_value(),
        drafts_folder=cfg.imap.drafts_folder, sent_folder=cfg.imap.sent_folder,
    )
    api_key = cfg.llm_api_key.get_secret_value() if cfg.llm_api_key else None
    provider = make_provider(cfg.llm_provider, api_key)
    return build_runner(session, imap, provider)


@app.command()
def scheduler():
    """Run the periodic scheduler loop (foreground; for the scheduler container)."""
    cfg = _load_config()
    intervals = {
        "main": cfg.schedule_minutes,
        "feedback": cfg.feedback_minutes,
        "style": cfg.style_minutes,
    }
    typer.echo("Starting scheduler loop...")
    run_loop(_make_runner, intervals)


if __name__ == "__main__":
    app()
