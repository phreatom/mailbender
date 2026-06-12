from typer.testing import CliRunner
from mailbender.server_cli.main import app

runner = CliRunner()


def test_scheduler_command_invokes_run_loop(monkeypatch):
    from mailbender.server_cli import main

    captured = {}

    def fake_run_loop(build_runner_fn, intervals, **kwargs):
        captured["intervals"] = intervals

    class FakeCfg:
        schedule_minutes = 15
        feedback_minutes = 60
        style_minutes = 0

    monkeypatch.setattr(main, "_load_config", lambda: FakeCfg())
    monkeypatch.setattr(main, "run_loop", fake_run_loop)
    monkeypatch.setattr(main, "_make_runner", lambda: object())
    result = runner.invoke(app, ["scheduler"])
    assert result.exit_code == 0
    assert captured["intervals"] == {"main": 15, "feedback": 60, "style": 0}
