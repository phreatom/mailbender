from sqlalchemy import select
from mailbender.llm.provider import LLMProvider, Email
from mailbender.store.models import ReferenceDraft


class DraftGenerator:
    def __init__(self, provider: LLMProvider, imap_client, session):
        self.provider = provider
        self.imap = imap_client
        self.session = session

    def generate(self, email: Email, style_examples: list[str]) -> str:
        existing = self.session.execute(
            select(ReferenceDraft).where(ReferenceDraft.source_uid == email.uid)
        ).scalar_one_or_none()
        if existing is not None:
            # Already drafted for this mail (e.g. a prior run committed the
            # reference but failed before mark_processed). Don't append again.
            return existing.content
        content = self.provider.generate_draft(email, style_examples)
        subject = email.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        self.imap.append_draft(subject, content)
        self.session.add(ReferenceDraft(
            source_uid=email.uid,
            message_id=email.message_id,
            content=content,
        ))
        self.session.commit()
        return content
