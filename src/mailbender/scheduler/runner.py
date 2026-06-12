from mailbender.store.repository import Repository
from mailbender.pipeline.classifier import Classifier
from mailbender.pipeline.prioritizer import Prioritizer
from mailbender.pipeline.mover import Mover
from mailbender.pipeline.draft_generator import DraftGenerator
from mailbender.pipeline.indexer import Indexer
from mailbender.audit.log import AuditLogger
from mailbender.learning.style_learner import StyleLearner
from mailbender.learning.feedback_learner import FeedbackLearner


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
                self.repo.record_run_step("main", email.uid, "classify",
                                          "success", category)
                priority = self.prioritizer.prioritize(email)
                self.repo.record_run_step("main", email.uid, "prioritize",
                                          "success", priority)
                self.indexer.index(email)
                self.repo.record_run_step("main", email.uid, "index", "success")
                moved = self.mover.maybe_move(email.uid, category)
                self.repo.record_run_step("main", email.uid, "move",
                                          "success" if moved else "skipped")
                drafted = False
                if category == self.reply_category:
                    self.draft_generator.generate(email, self.style_examples)
                    self.audit.record("scheduler", "draft_append", email.uid)
                    self.repo.record_run_step("main", email.uid, "draft", "success")
                    drafted = True
                else:
                    self.repo.record_run_step("main", email.uid, "draft", "skipped")
                self.repo.mark_processed(
                    email.uid, category, priority, moved, drafted)
            except Exception:  # per-mail isolation
                self.audit.record("scheduler", "process_error",
                                  email.uid, result="error")
                self.repo.record_run_step("main", email.uid, "process", "error")
                continue
        self.repo.record_run_step("main", None, "run", "success")

    def run_style(self):
        StyleLearner(self.imap, self.session).bootstrap()
        self.repo.record_run_step("style", None, "run", "success")

    def run_feedback(self):
        FeedbackLearner(self.imap, self.session).run()
        self.repo.record_run_step("feedback", None, "run", "success")
