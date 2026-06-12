from mailbender.llm.provider import LLMProvider, Email


class Classifier:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def classify(self, email: Email, categories: list[str]) -> str:
        result = self.provider.classify(email, categories)
        if result not in categories:
            return "unklassifiziert"
        return result
