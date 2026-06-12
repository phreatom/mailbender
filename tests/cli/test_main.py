from typer.testing import CliRunner
from mailagent.cli.main import app

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_categories_list_command(monkeypatch):
    from mailagent.cli import main

    class FakeRepo:
        def list_categories(self):
            class C:
                name = "Newsletter"
            return [C()]

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    result = runner.invoke(app, ["categories"])
    assert result.exit_code == 0
    assert "Newsletter" in result.stdout
