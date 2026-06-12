from mailbender.llm.provider import LLMProvider, Email

VALID = {"high", "medium", "low"}


class Prioritizer:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def prioritize(self, email: Email) -> str:
        result = self.provider.prioritize(email)
        return result if result in VALID else "medium"
