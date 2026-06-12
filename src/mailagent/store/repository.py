from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from mailagent.store.models import ProcessedMail, Category


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def is_processed(self, uid: str) -> bool:
        stmt = select(ProcessedMail).where(ProcessedMail.uid == uid)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def mark_processed(self, uid, category, priority, moved, drafted):
        stmt = insert(ProcessedMail).values(
            uid=uid, category=category, priority=priority,
            moved=moved, drafted=drafted,
        ).on_conflict_do_nothing(index_elements=["uid"])
        self.session.execute(stmt)
        self.session.commit()

    def count_processed(self) -> int:
        return self.session.execute(
            select(func.count()).select_from(ProcessedMail)
        ).scalar_one()

    def add_category(self, name: str, description: str = ""):
        stmt = insert(Category).values(
            name=name, description=description
        ).on_conflict_do_nothing(index_elements=["name"])
        self.session.execute(stmt)
        self.session.commit()

    def list_categories(self):
        return self.session.execute(select(Category)).scalars().all()

    def remove_category(self, name: str) -> bool:
        stmt = select(Category).where(Category.name == name)
        category = self.session.execute(stmt).scalar_one_or_none()
        if category is None:
            return False
        self.session.delete(category)
        self.session.commit()
        return True
