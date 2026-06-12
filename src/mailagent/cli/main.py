import typer
from mailagent import __version__
from mailagent.scheduler.loop import run_loop

app = typer.Typer(help="Mailagent CLI")


def _make_session(cfg):
    from mailagent.store.db import make_engine, make_session_factory
    engine = make_engine(cfg.database_url)
    return make_session_factory(engine)()


def _make_repo():
    from mailagent.config import load_config
    from mailagent.store.repository import Repository
    cfg = load_config()
    return Repository(_make_session(cfg))


def _load_config():
    from mailagent.config import load_config
    return load_config()


def _make_runner():
    from mailagent.config import load_config
    from mailagent.imap.client import ImapClient
    from mailagent.llm.factory import make_provider
    from mailagent.scheduler.wiring import build_runner
    cfg = load_config()
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
def version():
    """Print the version."""
    typer.echo(__version__)


@app.command()
def categories():
    """List configured categories."""
    repo = _make_repo()
    for c in repo.list_categories():
        typer.echo(c.name)


@app.command("add-category")
def add_category(name: str, description: str = ""):
    """Add a category."""
    repo = _make_repo()
    repo.add_category(name, description)
    typer.echo(f"Added category: {name}")


@app.command("remove-category")
def remove_category(name: str):
    """Remove a category by name."""
    repo = _make_repo()
    if repo.remove_category(name):
        typer.echo(f"Removed category: {name}")
    else:
        typer.echo(f"No such category: {name}")
        raise typer.Exit(code=1)


@app.command("seed-categories")
def seed_categories():
    """Add the default category set (idempotent)."""
    from mailagent.categories import seed_default_categories
    repo = _make_repo()
    added = seed_default_categories(repo)
    typer.echo(f"Seeded {added} categories.")


@app.command()
def run():
    """Trigger a main run now."""
    runner = _make_runner()
    runner.run_main()
    typer.echo("Main run complete.")


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


@app.command("run-style")
def run_style():
    """Bootstrap the writing-style profile from the Sent folder now."""
    _make_runner().run_style()
    typer.echo("Style run complete.")


@app.command("run-feedback")
def run_feedback():
    """Run the draft-vs-sent feedback pass now."""
    _make_runner().run_feedback()
    typer.echo("Feedback run complete.")


if __name__ == "__main__":
    app()
