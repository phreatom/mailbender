from mailagent.llm.factory import make_provider
from mailagent.llm.fake import FakeLLMProvider


def test_factory_returns_fake():
    provider = make_provider("fake", api_key=None)
    assert isinstance(provider, FakeLLMProvider)


def test_factory_unknown_raises():
    import pytest
    with pytest.raises(ValueError):
        make_provider("nope", api_key=None)
