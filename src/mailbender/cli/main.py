import typer
from rich.console import Console

from mailbender import __version__
from mailbender.client import render
from mailbender.client.config import (
    ClientConfig, resolve_config, save_config, delete_config, config_path,
)
from mailbender.client.api import ApiClient, ApiError

app = typer.Typer(help="Mailbender CLI — a thin client for the self-hosted API.")


class Ctx:
    def __init__(self, json=False, url=None, token=None, verbose=False):
        self.json = json
        self.url = url
        self.token = token
        self.verbose = verbose


def _version_callback(value: bool):
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    json: bool = typer.Option(False, "--json", help="Emit raw JSON for scripting."),
    url: str = typer.Option(None, "--url", help="API base URL (overrides config/env)."),
    token: str = typer.Option(None, "--token", help="API token (overrides config/env)."),
    verbose: bool = typer.Option(False, "--verbose", help="Show tracebacks on error."),
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show version and exit."),
):
    ctx.obj = Ctx(json=json, url=url, token=token, verbose=verbose)


def _client_factory(cfg: ClientConfig) -> ApiClient:
    return ApiClient(cfg)


def _api(ctx: typer.Context, fn):
    """Resolve config, build the client, call fn(client), translate errors."""
    o: Ctx = ctx.obj
    try:
        cfg = resolve_config(flag_url=o.url, flag_token=o.token)
        with _client_factory(cfg) as client:
            return fn(client)
    except ApiError as exc:
        render.error(exc.message)
        if o.verbose:
            raise
        raise typer.Exit(code=exc.exit_code)


@app.command()
def version():
    """Print the client version."""
    typer.echo(__version__)


@app.command()
def login(
    url: str = typer.Option(None, "--url"),
    token: str = typer.Option(None, "--token"),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip reachability/token check."),
):
    """Configure the API URL and token (writes ~/.config/mailbender/config.toml)."""
    url = url or typer.prompt("API URL", default="http://localhost:8000")
    token = token or typer.prompt("API token", hide_input=True)
    cfg = ClientConfig(url=url, token=token)
    if not no_verify:
        try:
            with _client_factory(cfg) as client:
                client.health()          # reachability
                client.categories_list()  # token check (401 if wrong)
        except ApiError as exc:
            render.error(f"login failed: {exc.message}")
            raise typer.Exit(code=1)
    path = save_config(cfg, path=config_path())
    typer.echo(f"Saved credentials to {path}")


@app.command()
def logout():
    """Remove the stored credentials."""
    if delete_config(path=config_path()):
        typer.echo("Logged out.")
    else:
        typer.echo("No stored credentials.")


@app.command()
def status(ctx: typer.Context):
    """Show the resolved API URL, whether a token is set, and reachability."""
    o: Ctx = ctx.obj
    cfg = resolve_config(flag_url=o.url, flag_token=o.token)
    reachable = False
    if cfg.url and cfg.token:
        try:
            with _client_factory(cfg) as client:
                client.health()
                reachable = True
        except ApiError:
            reachable = False
    info = {"url": cfg.url, "token_set": bool(cfg.token), "reachable": reachable}
    if o.json:
        render.emit_json(info)
    else:
        Console().print(
            f"url: {cfg.url or '(unset)'}\n"
            f"auth: {'configured' if cfg.token else 'not configured'}\n"
            f"reachable: {reachable}")


@app.command()
def chat(ctx: typer.Context, question: str):
    """Ask a question about the mailbox."""
    data = _api(ctx, lambda c: c.chat(question))
    render.chat(data, ctx.obj.json)


@app.command()
def run(ctx: typer.Context,
        type: str = typer.Option("main", "--type", help="main|style|feedback")):
    """Trigger a run now."""
    data = _api(ctx, lambda c: c.run(type))
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"{data.get('run_type', type)} run triggered.")


@app.command()
def priorities(ctx: typer.Context):
    """List processed mail sorted by priority."""
    data = _api(ctx, lambda c: c.priorities())
    render.priorities(data, ctx.obj.json)


@app.command()
def history(ctx: typer.Context, limit: int = typer.Option(50, "--limit")):
    """Show recent run history."""
    data = _api(ctx, lambda c: c.history(limit))
    render.history(data, ctx.obj.json)


@app.command()
def audit(ctx: typer.Context, limit: int = typer.Option(50, "--limit")):
    """Show recent audit-log entries."""
    data = _api(ctx, lambda c: c.audit(limit))
    render.audit(data, ctx.obj.json)


categories_app = typer.Typer(help="Manage categories.")
app.add_typer(categories_app, name="categories")


@categories_app.command("list")
def categories_list(ctx: typer.Context):
    """List configured categories."""
    data = _api(ctx, lambda c: c.categories_list())
    render.categories(data, ctx.obj.json)


@categories_app.command("add")
def categories_add(ctx: typer.Context, name: str,
                   description: str = typer.Option("", "--description")):
    """Add a category."""
    data = _api(ctx, lambda c: c.categories_add(name, description))
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"Added category: {name}")


@categories_app.command("remove")
def categories_remove(ctx: typer.Context, name: str):
    """Remove a category."""
    data = _api(ctx, lambda c: c.categories_remove(name))
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"Removed category: {name}")


@categories_app.command("seed")
def categories_seed(ctx: typer.Context):
    """Add the default category set (idempotent)."""
    data = _api(ctx, lambda c: c.categories_seed())
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"Seeded {data.get('added', 0)} categories.")


mappings_app = typer.Typer(help="Manage category-to-folder mappings.")
app.add_typer(mappings_app, name="mappings")


@mappings_app.command("list")
def mappings_list(ctx: typer.Context):
    """List category-to-folder mappings."""
    data = _api(ctx, lambda c: c.mappings_list())
    render.mappings(data, ctx.obj.json)


@mappings_app.command("add")
def mappings_add(ctx: typer.Context, category: str, folder: str):
    """Map a category to a target IMAP folder."""
    data = _api(ctx, lambda c: c.mappings_add(category, folder))
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"Mapped {category} -> {folder}")


@mappings_app.command("remove")
def mappings_remove(ctx: typer.Context, category: str):
    """Remove a category-to-folder mapping."""
    data = _api(ctx, lambda c: c.mappings_remove(category))
    if ctx.obj.json:
        render.emit_json(data)
    elif data.get("removed"):
        render.confirm(f"Removed mapping: {category}")
    else:
        render.error(f"No such mapping: {category}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
