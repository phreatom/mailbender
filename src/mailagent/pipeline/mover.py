class Mover:
    def __init__(self, imap_client, mapping: dict[str, str]):
        self.imap = imap_client
        self.mapping = mapping

    def maybe_move(self, uid: str, category: str) -> bool:
        target = self.mapping.get(category)
        if not target:
            return False
        self.imap.move(uid, target)
        return True
