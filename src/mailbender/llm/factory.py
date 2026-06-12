from mailbender.llm.fake import FakeLLMProvider


def make_provider(name: str, api_key):
    if name == "fake":
        return FakeLLMProvider()
    if name == "openai":
        from openai import OpenAI
        from mailbender.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(client=OpenAI(api_key=api_key))
    raise ValueError(f"Unknown provider: {name}")
