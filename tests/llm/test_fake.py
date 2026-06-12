from mailbender.llm.fake import FakeLLMProvider
from mailbender.llm.provider import Email


def test_fake_classify_returns_configured_category():
    provider = FakeLLMProvider(category="Rechnung", priority="high")
    email = Email(uid="1", subject="Invoice", sender="a@b.c", body="pay now")
    assert provider.classify(email, ["Rechnung", "Newsletter"]) == "Rechnung"


def test_fake_prioritize():
    provider = FakeLLMProvider(category="X", priority="high")
    email = Email(uid="1", subject="s", sender="a@b.c", body="b")
    assert provider.prioritize(email) == "high"


def test_fake_generate_draft_includes_style():
    provider = FakeLLMProvider(draft="Hallo, danke!")
    email = Email(uid="1", subject="s", sender="a@b.c", body="b")
    draft = provider.generate_draft(email, style_examples=["best regards"])
    assert draft == "Hallo, danke!"


def test_fake_embed_returns_fixed_dimension():
    provider = FakeLLMProvider()
    vec = provider.embed("some text")
    assert len(vec) == 1536


def test_fake_chat_returns_answer_with_sources():
    provider = FakeLLMProvider(chat_answer="Sarah said yes.")
    answer = provider.chat("What did Sarah say?", context=["Sarah: yes"])
    assert "Sarah" in answer
