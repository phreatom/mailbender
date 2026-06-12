from difflib import SequenceMatcher
from sqlalchemy import select
from mailbender.store.models import ReferenceDraft, StyleExample


class FeedbackLearner:
    def __init__(self, imap_client, session):
        self.imap = imap_client
        self.session = session

    def run(self) -> int:
        sent = self.imap.fetch_folder(self.imap.sent_folder)
        matched = 0
        for email in sent:
            ref = self._match(email)
            if ref is None:
                continue
            ratio = SequenceMatcher(None, ref.content, email.body).ratio()
            # more editing (lower ratio) -> stronger correction signal
            weight = 1.0 + (1.0 - ratio)
            self.session.add(StyleExample(
                content=email.body, source="feedback", weight=weight,
            ))
            matched += 1
        self.session.commit()
        return matched

    def _match(self, email) -> ReferenceDraft | None:
        if not email.in_reply_to:
            return None
        stmt = select(ReferenceDraft).where(
            ReferenceDraft.message_id == email.in_reply_to)
        return self.session.execute(stmt).scalar_one_or_none()
