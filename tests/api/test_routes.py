from mailagent.api import routes
from mailagent.chat.chat import ChatAnswer, ChatSource


class FakeChat:
    def ask(self, question):
        return ChatAnswer(text="answer",
                          sources=[ChatSource(uid="1", subject="s")])


def test_chat_answer_shape():
    out = routes.chat_answer(FakeChat(), "q")
    assert out == {"text": "answer", "sources": [{"uid": "1", "subject": "s"}]}


def test_priorities_shape():
    class P:
        uid = "1"; priority = "high"; category = "X"

    class Repo:
        def processed_by_priority(self):
            return [P()]

    assert routes.priorities(Repo()) == [
        {"uid": "1", "priority": "high", "category": "X"}]


def test_mappings_shape_and_mutations():
    store = {}

    class M:
        def __init__(self, c, f):
            self.category_name = c; self.target_folder = f

    class Repo:
        def list_mappings(self):
            return [M(c, f) for c, f in store.items()]

        def add_mapping(self, c, f):
            store[c] = f

        def remove_mapping(self, c):
            return store.pop(c, None) is not None

    assert routes.list_mappings(Repo()) == []
    assert routes.add_mapping(Repo(), "N", "F") == {"category": "N", "folder": "F"}
    assert routes.list_mappings(Repo()) == [{"category": "N", "folder": "F"}]
    assert routes.remove_mapping(Repo(), "N") == {"removed": True}
