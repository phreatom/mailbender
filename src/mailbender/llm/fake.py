from mailbender.llm.provider import Email


class FakeLLMProvider:
    def __init__(self, category="Sonstiges", priority="medium",
                 draft="(draft)", chat_answer="(answer)"):
        self._category = category
        self._priority = priority
        self._draft = draft
        self._chat_answer = chat_answer

    def classify(self, email: Email, categories: list[str]) -> str:
        return self._category

    def prioritize(self, email: Email) -> str:
        return self._priority

    def generate_draft(self, email: Email, style_examples: list[str]) -> str:
        return self._draft

    def embed(self, text: str) -> list[float]:
        return [0.0] * 1536

    def chat(self, question: str, context: list[str],
             history: list[tuple[str, str]] | None = None) -> str:
        if not context:
            return "Keine passende Information gefunden."
        return self._chat_answer
