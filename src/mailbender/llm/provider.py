from dataclasses import dataclass
from typing import Protocol


@dataclass
class Email:
    uid: str
    subject: str
    sender: str
    body: str
    message_id: str = ""
    in_reply_to: str = ""


class LLMProvider(Protocol):
    def classify(self, email: Email, categories: list[str]) -> str: ...
    def prioritize(self, email: Email) -> str: ...
    def generate_draft(self, email: Email, style_examples: list[str]) -> str: ...
    def embed(self, text: str) -> list[float]: ...
    def chat(self, question: str, context: list[str],
             history: list[tuple[str, str]] | None = None) -> str: ...
