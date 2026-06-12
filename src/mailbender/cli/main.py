import typer
from mailbender import __version__
from mailbender.scheduler.loop import run_loop

app = typer.Typer(help="Mailbender CLI")


def _make_session(cfg):
    from mailbender.store.db import make_engine, make_session_factory
    engine = make_engine(cfg.database_url)
    return make_session_factory(engine)()


def _make_repo():
    from mailbender.config import load_config
    from mailbender.store.repository import Repository
    cfg = load_config()
    return Repository(_make_session(cfg))


def _load_config():
    from mailbender.config import load_config
    return load_config()


def _make_chat():
    from mailbender.config import load_config
    from mailbender.llm.factory import make_provider
    from mailbender.chat.chat import Chat
    cfg = load_config()
    session = _make_session(cfg)
    api_key = cfg.llm_api_key.get_secret_value() if cfg.llm_api_key else None
    provider = make_provider(cfg.llm_provider, api_key)
    return Chat(provider, session)


def _make_runner():
    from mailbender.config import load_config
    from mailbender.imap.client import ImapClient
    from mailbender.llm.factory import make_provider
    from mailbender.scheduler.wiring import build_runner
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
    from mailbender.categories import seed_default_categories
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


@app.command()
def chat(question: str):
    """Ask a question about the mailbox."""
    answer = _make_chat().ask(question)
    typer.echo(answer.text)
    if answer.sources:
        typer.echo("Quellen:")
        for s in answer.sources:
            typer.echo(f"  [{s.uid}] {s.subject}")


@app.command()
def history(limit: int = 50):
    """Show recent run history."""
    repo = _make_repo()
    for r in repo.recent_runs(limit):
        typer.echo(f"{r.created_at:%Y-%m-%d %H:%M} {r.run_type:8} "
                   f"{str(r.uid):8} {r.step:10} {r.result:8} {r.detail}")


@app.command()
def audit(limit: int = 50):
    """Show recent audit-log entries."""
    repo = _make_repo()
    for r in repo.recent_audit(limit):
        typer.echo(f"{r.created_at:%Y-%m-%d %H:%M} {r.actor:10} "
                   f"{r.action:16} {r.target:12} {r.result}")


@app.command()
def priorities():
    """List processed mail sorted by priority (high first)."""
    repo = _make_repo()
    marks = {"high": "!!!", "medium": "!", "low": " "}
    for p in repo.processed_by_priority():
        typer.echo(f"{marks.get(p.priority, ' '):3} {p.priority:7} "
                   f"[{p.uid}] {p.category}")


@app.command("add-mapping")
def add_mapping(category: str, folder: str):
    """Map a category to a target IMAP folder (upserts)."""
    _make_repo().add_mapping(category, folder)
    typer.echo(f"Mapped {category} -> {folder}")


@app.command()
def mappings():
    """List category-to-folder mappings."""
    for m in _make_repo().list_mappings():
        typer.echo(f"{m.category_name} -> {m.target_folder}")


@app.command("remove-mapping")
def remove_mapping(category: str):
    """Remove a category-to-folder mapping."""
    if _make_repo().remove_mapping(category):
        typer.echo(f"Removed mapping: {category}")
    else:
        typer.echo(f"No such mapping: {category}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
