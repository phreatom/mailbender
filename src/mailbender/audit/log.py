from mailbender.store.models import AuditLog


class AuditLogger:
    def __init__(self, session):
        self.session = session

    def record(self, actor: str, action: str, target: str = "",
               result: str = "success"):
        self.session.add(AuditLog(
            actor=actor, action=action, target=target, result=result,
        ))
        self.session.commit()
