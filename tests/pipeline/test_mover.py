from mailagent.pipeline.mover import Mover


class FakeImap:
    def __init__(self):
        self.moved = []

    def move(self, uid, target_folder, source_folder="INBOX"):
        self.moved.append((uid, target_folder))


def test_move_applies_mapping():
    imap = FakeImap()
    mover = Mover(imap, mapping={"Newsletter": "Archive/News"})
    moved = mover.maybe_move("uid-1", "Newsletter")
    assert moved is True
    assert imap.moved == [("uid-1", "Archive/News")]


def test_no_mapping_means_no_move():
    imap = FakeImap()
    mover = Mover(imap, mapping={"Newsletter": "Archive/News"})
    moved = mover.maybe_move("uid-2", "Rechnung")
    assert moved is False
    assert imap.moved == []
