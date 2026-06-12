import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

POSTGRES_URL = "postgresql+psycopg://postgres:postgres@localhost:55432/mailagent_test"


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return str(pytestconfig.rootdir / "tests" / "docker-compose.test.yml")


@pytest.fixture(scope="session")
def db_engine(docker_services):
    docker_services.wait_until_responsive(
        timeout=60.0, pause=1.0, check=lambda: _can_connect(POSTGRES_URL)
    )
    engine = create_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    return engine


def _can_connect(url: str) -> bool:
    try:
        create_engine(url).connect().close()
        return True
    except Exception:
        return False


@pytest.fixture
def db_session(db_engine):
    # Wrap each test in an outer transaction bound to a single connection.
    # join_transaction_mode="create_savepoint" makes in-test session.commit()
    # release a savepoint rather than commit the outer transaction, so the
    # final rollback undoes everything and tests stay isolated.
    connection = db_engine.connect()
    trans = connection.begin()
    Session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    session = Session()
    yield session
    session.close()
    trans.rollback()
    connection.close()
