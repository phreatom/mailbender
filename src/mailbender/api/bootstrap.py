from sqlalchemy.orm import scoped_session, sessionmaker
from mailbender.config import load_config
from mailbender.store.db import make_engine
from mailbender.store.repository import Repository
from mailbender.api.app import create_app


def _build_imap(cfg):
    from mailbender.imap.client import ImapClient
    return ImapClient(
        host=cfg.imap.host, port=cfg.imap.port, user=cfg.imap.user,
        password=cfg.imap.password.get_secret_value(),
        drafts_folder=cfg.imap.drafts_folder, sent_folder=cfg.imap.sent_folder,
    )


def _build_provider(cfg):
    from mailbender.llm.factory import make_provider
    api_key = cfg.llm_api_key.get_secret_value() if cfg.llm_api_key else None
    return make_provider(cfg.llm_provider, api_key)


def _build_chat(cfg, session):
    from mailbender.chat.chat import Chat
    return Chat(_build_provider(cfg), session)


def _build_runner(cfg, session):
    from mailbender.scheduler.wiring import build_runner
    return build_runner(session, _build_imap(cfg), _build_provider(cfg))


def production_app():
    """Zero-arg app factory for `uvicorn --factory`.

    Reads Config, wires the API's injected factories to a request-scoped
    session, and removes the session after each request so connections don't
    leak. This is the production entrypoint; tests use create_app directly.
    """
    cfg = load_config()
    engine = make_engine(cfg.database_url)
    SessionLocal = scoped_session(
        sessionmaker(bind=engine, expire_on_commit=False))
    token = cfg.api_token.get_secret_value() if cfg.api_token else ""
    app = create_app(api_token=token)

    app.state.repo_factory = lambda: Repository(SessionLocal())
    app.state.chat_factory = lambda: _build_chat(cfg, SessionLocal())
    app.state.runner_factory = lambda: _build_runner(cfg, SessionLocal())

    @app.middleware("http")
    async def _remove_session(request, call_next):
        try:
            return await call_next(request)
        finally:
            SessionLocal.remove()

    return app
