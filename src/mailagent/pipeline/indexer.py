from sqlalchemy.dialects.postgresql import insert
from mailagent.llm.provider import LLMProvider, Email
from mailagent.store.models import MailIndex


class Indexer:
    def __init__(self, provider: LLMProvider, session):
        self.provider = provider
        self.session = session

    def index(self, email: Email):
        text = f"{email.subject}\n{email.body}"
        embedding = self.provider.embed(text)
        stmt = insert(MailIndex).values(
            uid=email.uid, subject=email.subject, sender=email.sender,
            body=email.body, embedding=embedding,
        ).on_conflict_do_nothing(index_elements=["uid"])
        self.session.execute(stmt)
        self.session.commit()
