import time

from mailbender.llm.provider import Email
from mailbender.util.retry import retry

CLASSIFY_PROMPT = (
    "Classify this email into exactly one of these categories: {categories}.\n"
    "Reply with only the category name.\n\nSubject: {subject}\n\n{body}"
)
PRIORITY_PROMPT = (
    "Rate the urgency of this email as exactly one word: high, medium, or low.\n\n"
    "Subject: {subject}\n\n{body}"
)
DRAFT_PROMPT = (
    "Write a reply to the email below. Match the writing style shown in these "
    "examples:\n{style}\n\n---\nEmail:\nSubject: {subject}\n\n{body}"
)
CHAT_PROMPT = (
    "Answer the question using only the email context below. If the context "
    "does not contain the answer, say you found no matching information.\n\n"
    "Context:\n{context}\n\nQuestion: {question}"
)


class OpenAIProvider:
    def __init__(self, client, model="gpt-4o-mini",
                 embed_model="text-embedding-3-small"):
        self.client = client
        self.model = model
        self.embed_model = embed_model

    def _chat(self, prompt: str) -> str:
        def call():
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content.strip()
        return retry(call, sleep=time.sleep)

    def classify(self, email: Email, categories: list[str]) -> str:
        return self._chat(CLASSIFY_PROMPT.format(
            categories=", ".join(categories),
            subject=email.subject, body=email.body))

    def prioritize(self, email: Email) -> str:
        return self._chat(PRIORITY_PROMPT.format(
            subject=email.subject, body=email.body)).lower()

    def generate_draft(self, email: Email, style_examples: list[str]) -> str:
        return self._chat(DRAFT_PROMPT.format(
            style="\n---\n".join(style_examples),
            subject=email.subject, body=email.body))

    def embed(self, text: str) -> list[float]:
        def call():
            resp = self.client.embeddings.create(
                model=self.embed_model, input=text)
            return list(resp.data[0].embedding)
        return retry(call, sleep=time.sleep)

    def chat(self, question: str, context: list[str],
             history: list[tuple[str, str]] | None = None) -> str:
        convo = ""
        if history:
            convo = "\n".join(f"{role}: {text}" for role, text in history) + "\n\n"
        return self._chat(convo + CHAT_PROMPT.format(
            context="\n\n".join(context), question=question))
