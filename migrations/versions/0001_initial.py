"""initial schema"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    from mailbender.store.models import Base
    Base.metadata.create_all(op.get_bind())


def downgrade():
    from mailbender.store.models import Base
    Base.metadata.drop_all(op.get_bind())
