from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


def make_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_scope(session_factory) -> Session:
    return session_factory()
