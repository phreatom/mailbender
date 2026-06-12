from mailagent.llm.provider import LLMProvider, Email
from mailagent.store.models import ReferenceDraft


class DraftGenerator:
    def __init__(self, provider: LLMProvider, imap_client, session):
        self.provider = provider
        self.imap = imap_client
        self.session = session

    def generate(self, email: Email, style_examples: list[str]) -> str:
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
