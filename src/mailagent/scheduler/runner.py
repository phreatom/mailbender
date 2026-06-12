from mailagent.store.repository import Repository
from mailagent.pipeline.classifier import Classifier
from mailagent.pipeline.prioritizer import Prioritizer
from mailagent.pipeline.mover import Mover
from mailagent.pipeline.draft_generator import DraftGenerator
from mailagent.pipeline.indexer import Indexer
from mailagent.audit.log import AuditLogger
from mailagent.learning.style_learner import StyleLearner
from mailagent.learning.feedback_learner import FeedbackLearner


class Runner:
    def __init__(self, imap, provider, session, categories, mapping,
                 reply_category, style_examples):
        self.imap = imap
        self.session = session
        self.repo = Repository(session)
        self.categories = categories
        self.reply_category = reply_category
        self.style_examples = style_examples
        self.classifier = Classifier(provider)
        self.prioritizer = Prioritizer(provider)
        self.mover = Mover(imap, mapping)
        self.draft_generator = DraftGenerator(provider, imap, session)
        self.indexer = Indexer(provider, session)
        self.audit = AuditLogger(session)

    def run_main(self):
        for email in self.imap.fetch_inbox():
            if self.repo.is_processed(email.uid):
                continue
            try:
                category = self.classifier.classify(email, self.categories)
                priority = self.prioritizer.prioritize(email)
                self.indexer.index(email)
                moved = self.mover.maybe_move(email.uid, category)
                drafted = False
                if category == self.reply_category:
                    self.draft_generator.generate(email, self.style_examples)
                    self.audit.record("scheduler", "draft_append", email.uid)
                    drafted = True
                self.repo.mark_processed(
                    email.uid, category, priority, moved, drafted)
            except Exception as exc:  # per-mail isolation
                self.audit.record("scheduler", "process_error",
                                  email.uid, result="error")
                continue

    def run_style(self):
        StyleLearner(self.imap, self.session).bootstrap()

    def run_feedback(self):
        FeedbackLearner(self.imap, self.session).run()
