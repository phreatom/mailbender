import typer
from mailagent import __version__

app = typer.Typer(help="Mailagent CLI")


def _make_repo():
    from mailagent.config import load_config
    from mailagent.store.db import make_engine, make_session_factory
    from mailagent.store.repository import Repository
    cfg = load_config()
    engine = make_engine(cfg.database_url)
    session = make_session_factory(engine)()
    return Repository(session)


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


@app.command()
def run():
    """Trigger a main run now."""
    typer.echo("Triggering main run...")
    # Wiring to Runner is done in deployment task; kept thin here.


if __name__ == "__main__":
    app()
