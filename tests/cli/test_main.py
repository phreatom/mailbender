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


def test_scheduler_command_invokes_run_loop(monkeypatch):
    from mailagent.cli import main

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


def test_run_style_command(monkeypatch):
    from mailagent.cli import main

    class FakeRunner:
        def __init__(self):
            self.called = False

        def run_style(self):
            self.called = True

    fake = FakeRunner()
    monkeypatch.setattr(main, "_make_runner", lambda: fake)
    result = runner.invoke(app, ["run-style"])
    assert result.exit_code == 0
    assert fake.called is True


def test_chat_command(monkeypatch):
    from mailagent.cli import main
    from mailagent.chat.chat import ChatAnswer, ChatSource

    class FakeChat:
        def ask(self, question):
            return ChatAnswer(text="Sarah approved it.",
                              sources=[ChatSource(uid="1", subject="Budget")])

    monkeypatch.setattr(main, "_make_chat", lambda: FakeChat())
    result = runner.invoke(app, ["chat", "What did Sarah say?"])
    assert result.exit_code == 0
    assert "Sarah approved it." in result.stdout
    assert "1" in result.stdout


def test_history_command(monkeypatch):
    from mailagent.cli import main

    class Row:
        run_type = "main"; uid = "1"; step = "classify"
        result = "success"; detail = "Newsletter"

    class FakeRepo:
        def recent_runs(self, limit=50):
            return [Row()]

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "classify" in result.stdout


def test_audit_command(monkeypatch):
    from mailagent.cli import main

    class Row:
        actor = "scheduler"; action = "draft_append"
        target = "uid-1"; result = "success"

    class FakeRepo:
        def recent_audit(self, limit=50):
            return [Row()]

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    result = runner.invoke(app, ["audit"])
    assert result.exit_code == 0
    assert "draft_append" in result.stdout


def test_priorities_command(monkeypatch):
    from mailagent.cli import main

    class Row:
        def __init__(self, uid, priority, category):
            self.uid = uid; self.priority = priority; self.category = category

    class FakeRepo:
        def processed_by_priority(self):
            return [Row("1", "high", "Antwort nötig"),
                    Row("2", "low", "Newsletter")]

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    result = runner.invoke(app, ["priorities"])
    assert result.exit_code == 0
    assert "high" in result.stdout
    assert result.stdout.index("high") < result.stdout.index("low")


def test_mapping_commands(monkeypatch):
    from mailagent.cli import main

    store = {}

    class M:
        def __init__(self, c, f):
            self.category_name = c; self.target_folder = f

    class FakeRepo:
        def add_mapping(self, category, folder):
            store[category] = folder

        def list_mappings(self):
            return [M(c, f) for c, f in store.items()]

        def remove_mapping(self, category):
            return store.pop(category, None) is not None

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    assert runner.invoke(app, ["add-mapping", "Newsletter", "Archive/News"]).exit_code == 0
    out = runner.invoke(app, ["mappings"])
    assert "Newsletter" in out.stdout and "Archive/News" in out.stdout
    assert runner.invoke(app, ["remove-mapping", "Newsletter"]).exit_code == 0
    assert runner.invoke(app, ["remove-mapping", "Newsletter"]).exit_code == 1
