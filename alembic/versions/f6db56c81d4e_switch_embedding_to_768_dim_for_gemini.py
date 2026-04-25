"""switch embedding to 768 dim for gemini

Revision ID: f6db56c81d4e
Revises: bbcedf249985
Create Date: 2026-04-22 12:33:28.647802

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f6db56c81d4e"
down_revision: Union[str, None] = "bbcedf249985"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop IVFFlat index (tied to column type), truncate table (empty in practice),
    # resize column, recreate index.
    op.execute("DROP INDEX IF EXISTS ix_semantic_cache_entries_embedding")
    op.execute("TRUNCATE TABLE semantic_cache_entries")
    op.execute("ALTER TABLE semantic_cache_entries DROP COLUMN embedding")
    op.execute(
        "ALTER TABLE semantic_cache_entries ADD COLUMN embedding vector(768) NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_semantic_cache_entries_embedding "
        "ON semantic_cache_entries USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_semantic_cache_entries_embedding")
    op.execute("TRUNCATE TABLE semantic_cache_entries")
    op.execute("ALTER TABLE semantic_cache_entries DROP COLUMN embedding")
    op.execute(
        "ALTER TABLE semantic_cache_entries ADD COLUMN embedding vector(1536) NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_semantic_cache_entries_embedding "
        "ON semantic_cache_entries USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
