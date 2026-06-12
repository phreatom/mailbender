from sqlalchemy import select
from mailagent.store.models import FolderMapping
from mailagent.store.repository import Repository
from mailagent.learning.style_learner import StyleLearner
from mailagent.scheduler.runner import Runner

DEFAULT_REPLY_CATEGORY = "Antwort nötig"


def build_runner(session, imap, provider, reply_category=DEFAULT_REPLY_CATEGORY):
    """Assemble a Runner from current DB state (categories, folder mapping,
    learned style examples) plus the given imap client and llm provider.
    """
    repo = Repository(session)
    categories = [c.name for c in repo.list_categories()]
    mapping = {
        fm.category_name: fm.target_folder
        for fm in session.execute(select(FolderMapping)).scalars().all()
    }
    style_examples = StyleLearner(imap, session).get_style_examples()
    return Runner(
        imap=imap, provider=provider, session=session,
        categories=categories, mapping=mapping,
        reply_category=reply_category, style_examples=style_examples,
    )
