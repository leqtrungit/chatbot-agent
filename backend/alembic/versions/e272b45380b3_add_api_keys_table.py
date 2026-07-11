"""add api keys table

Revision ID: e272b45380b3
Revises: 542eb8b7605b
Create Date: 2026-07-11 14:38:38.119616

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e272b45380b3'
down_revision: Union[str, Sequence[str], None] = '542eb8b7605b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: autogenerate also proposed dropping ix_document_chunks_document_id,
    # ix_document_chunks_embedding_hnsw and ix_documents_domain_id — a known
    # false positive (see .claude/skills/db-migration/SKILL.md): those
    # indexes are created via raw op.execute()/op.create_index() in
    # 542eb8b7605b and aren't represented in SQLAlchemy model metadata, so
    # autogenerate's DB-vs-metadata diff mistakes them for removed indexes.
    # Intentionally not touching them here.
    op.create_table(
        'api_keys',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('key_prefix', sa.String(length=8), nullable=False),
        sa.Column('rate_limit_per_minute', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('api_keys')
