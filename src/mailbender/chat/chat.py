from dataclasses import dataclass
from sqlalchemy import select
from mailbender.llm.provider import LLMProvider
from mailbender.store.models import MailIndex


@dataclass
class ChatSource:
    uid: str
    subject: str


@dataclass
class ChatAnswer:
    text: str
    sources: list[ChatSource]


class Chat:
    def __init__(self, provider: LLMProvider, session, top_k: int = 5):
        self.provider = provider
        self.session = session
        self.top_k = top_k

    def ask(self, question: str, history: list[tuple[str, str]] | None = None) -> ChatAnswer:
        query_vec = self.provider.embed(question)
        stmt = (select(MailIndex)
                .order_by(MailIndex.embedding.cosine_distance(query_vec))
                .limit(self.top_k))
        rows = self.session.execute(stmt).scalars().all()
        if not rows:
            return ChatAnswer(text="Keine passende Information gefunden.",
                              sources=[])
        context = [f"{r.sender}: {r.body}" for r in rows]
        text = self.provider.chat(question, context, history=history or [])
        sources = [ChatSource(uid=r.uid, subject=r.subject) for r in rows]
        return ChatAnswer(text=text, sources=sources)
