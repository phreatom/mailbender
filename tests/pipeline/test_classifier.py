from mailbender.llm.fake import FakeLLMProvider
from mailbender.llm.provider import Email
from mailbender.pipeline.classifier import Classifier
from mailbender.pipeline.prioritizer import Prioritizer

EMAIL = Email(uid="1", subject="s", sender="a@b.c", body="b")


def test_classifier_returns_known_category():
    clf = Classifier(FakeLLMProvider(category="Newsletter"))
    assert clf.classify(EMAIL, ["Newsletter", "Rechnung"]) == "Newsletter"


def test_classifier_unknown_category_falls_back():
    clf = Classifier(FakeLLMProvider(category="Bogus"))
    assert clf.classify(EMAIL, ["Newsletter"]) == "unklassifiziert"


def test_prioritizer_valid_level():
    pri = Prioritizer(FakeLLMProvider(priority="high"))
    assert pri.prioritize(EMAIL) == "high"


def test_prioritizer_invalid_defaults_medium():
    pri = Prioritizer(FakeLLMProvider(priority="banana"))
    assert pri.prioritize(EMAIL) == "medium"
