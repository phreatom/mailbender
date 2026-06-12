import secrets
import warnings
from sqlalchemy.orm import sessionmaker
from mailbender.config import load_config
from mailbender.store.db import make_engine
from mailbender.store.repository import Repository
from mailbender.api.app import create_app
from mailbender.web.security import WebSecurity
from mailbender.web.mount import mount_web


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

    Reads Config and wires the API's injected factories. Each factory opens a
    fresh Session per call (so no session state leaks across requests); the
    Session and its pooled connection are released when the per-request
    repo/runner/chat object is dereferenced after the response. This is correct
    for the single-user, low-concurrency self-hosted deployment.

    KNOWN LIMITATION / FOLLOW-UP: there is no *deterministic* per-request
    session teardown. A `scoped_session` + middleware approach does not work
    here because FastAPI runs sync routes in a worker thread while middleware
    runs on the event loop, so the thread-local scope is never cleaned in the
    right place (verified empirically). The correct fix is to make the session a
    request dependency (`Depends(get_session)`) and have endpoints pass it to
    the factories — that evolves the zero-arg factory seam and is tracked as a
    follow-up task. Run with a single uvicorn worker until then.
    """
    cfg = load_config()
    engine = make_engine(cfg.database_url)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    token = cfg.api_token.get_secret_value() if cfg.api_token else ""
    if not token:
        warnings.warn(
            "MAILBENDER_API_TOKEN is unset; the API will reject every request. "
            "Set it to enable authenticated access.")
    app = create_app(api_token=token)

    secret_key = cfg.secret_key.get_secret_value() if cfg.secret_key else ""
    if not secret_key:
        secret_key = secrets.token_urlsafe(32)
        warnings.warn(
            "MAILBENDER_SECRET_KEY is unset; using an ephemeral key. Web "
            "sessions will not survive restarts or span workers. Set it to "
            "stabilize sessions.")
    web_password = cfg.web_password.get_secret_value() if cfg.web_password else ""
    app.state.web_security = WebSecurity(secret_key=secret_key, password=web_password)
    mount_web(app)

    app.state.repo_factory = lambda: Repository(SessionLocal())
    app.state.chat_factory = lambda: _build_chat(cfg, SessionLocal())
    app.state.runner_factory = lambda: _build_runner(cfg, SessionLocal())

    return app
