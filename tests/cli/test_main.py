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


class RecordingRepo:
    def __init__(self, existing=None, remove_result=True):
        self._existing = list(existing or [])
        self._remove_result = remove_result
        self.added = []
        self.removed = []

    def list_categories(self):
        return [type("C", (), {"name": n})() for n in self._existing]

    def add_category(self, name, description=""):
        self.added.append((name, description))
        self._existing.append(name)

    def remove_category(self, name):
        self.removed.append(name)
        return self._remove_result


def test_add_category_command(monkeypatch):
    from mailagent.cli import main
    repo = RecordingRepo()
    monkeypatch.setattr(main, "_make_repo", lambda: repo)
    result = runner.invoke(app, ["add-category", "Projekt", "--description", "Work"])
    assert result.exit_code == 0
    assert ("Projekt", "Work") in repo.added
    assert "Projekt" in result.stdout


def test_remove_category_command(monkeypatch):
    from mailagent.cli import main
    repo = RecordingRepo(remove_result=True)
    monkeypatch.setattr(main, "_make_repo", lambda: repo)
    result = runner.invoke(app, ["remove-category", "Werbung"])
    assert result.exit_code == 0
    assert repo.removed == ["Werbung"]
    assert "Werbung" in result.stdout


def test_remove_missing_category_command_exits_nonzero(monkeypatch):
    from mailagent.cli import main
    repo = RecordingRepo(remove_result=False)
    monkeypatch.setattr(main, "_make_repo", lambda: repo)
    result = runner.invoke(app, ["remove-category", "Nope"])
    assert result.exit_code != 0


def test_seed_categories_command(monkeypatch):
    from mailagent.cli import main
    from mailagent.categories import DEFAULT_CATEGORIES
    repo = RecordingRepo()
    monkeypatch.setattr(main, "_make_repo", lambda: repo)
    result = runner.invoke(app, ["seed-categories"])
    assert result.exit_code == 0
    assert str(len(DEFAULT_CATEGORIES)) in result.stdout
    assert len(repo.added) == len(DEFAULT_CATEGORIES)


def test_run_command_invokes_run_main(monkeypatch):
    from mailagent.cli import main

    class FakeRunner:
        def __init__(self):
            self.called = False

        def run_main(self):
            self.called = True

    fake = FakeRunner()
    monkeypatch.setattr(main, "_make_runner", lambda: fake)
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 0
    assert fake.called is True
    assert "complete" in result.stdout.lower()
