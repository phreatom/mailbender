from sqlalchemy import select, desc
from mailbender.store.models import StyleExample


class StyleLearner:
    def __init__(self, imap_client, session, sample_size: int = 50):
        self.imap = imap_client
        self.session = session
        self.sample_size = sample_size

    def bootstrap(self) -> int:
        sent = self.imap.fetch_folder(self.imap.sent_folder)[: self.sample_size]
        count = 0
        for email in sent:
            self.session.add(StyleExample(
                content=email.body, source="bootstrap", weight=1.0,
            ))
            count += 1
        self.session.commit()
        return count

    def get_style_examples(self, limit: int = 10) -> list[str]:
        stmt = (select(StyleExample)
                .order_by(desc(StyleExample.weight))
                .limit(limit))
        return [r.content for r in self.session.execute(stmt).scalars().all()]
