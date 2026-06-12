import json as _json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# JSON to stdout; human chatter/errors to stderr so pipes stay clean.
# Width is auto-detected from the terminal (Rich falls back to $COLUMNS, then 80
# when not a TTY) so tables stay responsive when piped or in narrow terminals.
_out = Console()
_err = Console(stderr=True)


def emit_json(data) -> None:
    sys.stdout.write(_json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def error(message: str) -> None:
    _err.print(f"[red]error:[/] {message}")


def confirm(message: str) -> None:
    _out.print(f"[green]{message}[/]")


def table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    t = Table(title=title)
    for col in columns:
        t.add_column(col)
    for row in rows:
        t.add_row(*[str(c) for c in row])
    _out.print(t)


_PRIO_STYLE = {"high": "red", "medium": "yellow", "low": "dim"}


def priorities(rows, as_json: bool) -> None:
    if as_json:
        emit_json(rows)
        return
    t = Table(title="Priorities")
    t.add_column("priority"); t.add_column("uid"); t.add_column("category")
    for r in rows:
        style = _PRIO_STYLE.get(r.get("priority"), "")
        prio = f"[{style}]{r.get('priority')}[/]" if style else str(r.get("priority"))
        t.add_row(prio, str(r.get("uid")), str(r.get("category")))
    _out.print(t)


def history(rows, as_json: bool) -> None:
    if as_json:
        emit_json(rows)
        return
    table("Run history", ["created_at", "run_type", "uid", "step", "result", "detail"],
          [[r.get("created_at"), r.get("run_type"), r.get("uid"),
            r.get("step"), r.get("result"), r.get("detail")] for r in rows])


def audit(rows, as_json: bool) -> None:
    if as_json:
        emit_json(rows)
        return
    table("Audit log", ["created_at", "actor", "action", "target", "result"],
          [[r.get("created_at"), r.get("actor"), r.get("action"),
            r.get("target"), r.get("result")] for r in rows])


def categories(names, as_json: bool) -> None:
    if as_json:
        emit_json(names)
        return
    table("Categories", ["name"], [[n] for n in names])


def mappings(rows, as_json: bool) -> None:
    if as_json:
        emit_json(rows)
        return
    table("Mappings", ["category", "folder"],
          [[r.get("category"), r.get("folder")] for r in rows])


def chat(answer, as_json: bool) -> None:
    if as_json:
        emit_json(answer)
        return
    _out.print(Panel(answer.get("text", ""), title="Answer"))
    sources = answer.get("sources") or []
    if sources:
        table("Sources", ["uid", "subject"],
              [[s.get("uid"), s.get("subject")] for s in sources])
