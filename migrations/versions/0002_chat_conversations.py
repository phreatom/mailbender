"""chat conversations"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"


def upgrade():
    # `0001_initial` runs `Base.metadata.create_all`, which on current code
    # already creates these tables (the models exist in metadata). Guard each
    # create so a fresh install (tables already present) and an existing 0.1.0
    # deployment (tables absent) both upgrade cleanly.
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "conversation" not in existing:
        op.create_table(
            "conversation",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("title", sa.String(255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
    if "chat_message" not in existing:
        op.create_table(
            "chat_message",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("conversation_id", sa.Integer,
                      sa.ForeignKey("conversation.id"), nullable=False, index=True),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("text", sa.Text, nullable=False),
            sa.Column("sources_json", sa.Text, nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )


def downgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "chat_message" in existing:
        op.drop_table("chat_message")
    if "conversation" in existing:
        op.drop_table("conversation")
