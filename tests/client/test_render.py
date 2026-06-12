import json
from mailbender.client import render


def test_emit_json_writes_parsable_json(capsys):
    render.emit_json({"a": 1, "b": [2, 3]})
    out = capsys.readouterr().out
    assert json.loads(out) == {"a": 1, "b": [2, 3]}


def test_table_prints_rows(capsys):
    render.table("Cats", ["name"], [["Newsletter"], ["Rechnung"]])
    out = capsys.readouterr().out
    assert "Newsletter" in out and "Rechnung" in out


def test_priorities_human_shows_values(capsys):
    render.priorities([{"uid": "1", "priority": "high", "category": "X"}], as_json=False)
    out = capsys.readouterr().out
    assert "high" in out and "X" in out


def test_priorities_json(capsys):
    rows = [{"uid": "1", "priority": "high", "category": "X"}]
    render.priorities(rows, as_json=True)
    assert json.loads(capsys.readouterr().out) == rows


def test_chat_shows_text_and_sources(capsys):
    render.chat({"text": "Sarah approved", "sources": [{"uid": "1", "subject": "Budget"}]},
                as_json=False)
    out = capsys.readouterr().out
    assert "Sarah approved" in out and "Budget" in out
