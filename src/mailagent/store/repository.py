from sqlalchemy import select, func, desc, case
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from mailagent.store.models import (
    ProcessedMail, Category, RunHistory, AuditLog, FolderMapping,
)


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

    def record_run_step(self, run_type, uid, step, result, detail=""):
        self.session.add(RunHistory(
            run_type=run_type, uid=uid, step=step,
            result=result, detail=detail,
        ))
        self.session.commit()

    def last_run_at(self, run_type):
        stmt = (select(func.max(RunHistory.created_at))
                .where(RunHistory.run_type == run_type)
                .where(RunHistory.step == "run"))
        return self.session.execute(stmt).scalar_one_or_none()

    def recent_runs(self, limit: int = 50):
        stmt = (select(RunHistory)
                .order_by(desc(RunHistory.created_at))
                .limit(limit))
        return self.session.execute(stmt).scalars().all()

    def recent_audit(self, limit: int = 50):
        stmt = (select(AuditLog)
                .order_by(desc(AuditLog.created_at))
                .limit(limit))
        return self.session.execute(stmt).scalars().all()

    def processed_by_priority(self):
        order = case(
            (ProcessedMail.priority == "high", 0),
            (ProcessedMail.priority == "medium", 1),
            (ProcessedMail.priority == "low", 2),
            else_=3,
        )
        stmt = select(ProcessedMail).order_by(order, ProcessedMail.uid)
        return self.session.execute(stmt).scalars().all()

    def add_mapping(self, category_name: str, target_folder: str):
        stmt = insert(FolderMapping).values(
            category_name=category_name, target_folder=target_folder
        ).on_conflict_do_update(
            index_elements=["category_name"],
            set_={"target_folder": target_folder},
        )
        self.session.execute(stmt)
        self.session.commit()

    def list_mappings(self):
        return self.session.execute(select(FolderMapping)).scalars().all()

    def remove_mapping(self, category_name: str) -> bool:
        stmt = select(FolderMapping).where(
            FolderMapping.category_name == category_name)
        obj = self.session.execute(stmt).scalar_one_or_none()
        if obj is None:
            return False
        self.session.delete(obj)
        self.session.commit()
        return True
