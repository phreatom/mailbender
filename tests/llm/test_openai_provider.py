from mailagent.llm.openai_provider import OpenAIProvider
from mailagent.llm.provider import Email


class FakeChatResponse:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]


class FakeEmbeddingResponse:
    def __init__(self, vec):
        self.data = [type("D", (), {"embedding": vec})]


class FakeClient:
    def __init__(self, content="Newsletter", vec=None):
        self._content = content
        self._vec = vec or [0.0] * 1536

        class Chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return FakeChatResponse(content)
        class Embeddings:
            @staticmethod
            def create(**kwargs):
                return FakeEmbeddingResponse(self_vec=None)

        self.chat = Chat()
        self.embeddings = type("E", (), {
            "create": staticmethod(lambda **kw: FakeEmbeddingResponse(self._vec))
        })()


def test_classify_uses_chat_completion():
    provider = OpenAIProvider(client=FakeClient(content="Newsletter"))
    email = Email(uid="1", subject="s", sender="a@b.c", body="b")
    assert provider.classify(email, ["Newsletter", "Rechnung"]) == "Newsletter"


def test_embed_returns_vector():
    provider = OpenAIProvider(client=FakeClient(vec=[0.5] * 1536))
    assert provider.embed("text") == [0.5] * 1536


def test_chat_retries_transient_failure(monkeypatch):
    import mailagent.llm.openai_provider as mod
    from mailagent.llm.provider import Email

    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    state = {"n": 0}

    class FlakyClient:
        def __init__(self):
            outer = self

            class Chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        state["n"] += 1
                        if state["n"] < 2:
                            raise RuntimeError("transient")
                        return type("R", (), {"choices": [
                            type("C", (), {"message": type("M", (), {"content": "Newsletter"})})
                        ]})

            self.chat = Chat()

    provider = mod.OpenAIProvider(client=FlakyClient())
    email = Email(uid="1", subject="s", sender="a@b.c", body="b")
    assert provider.classify(email, ["Newsletter"]) == "Newsletter"
    assert state["n"] == 2
