"""add chat messages table

Revision ID: e717eccd3cad
Revises: e272b45380b3
Create Date: 2026-07-11 14:51:16.125140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e717eccd3cad'
down_revision: Union[str, Sequence[str], None] = 'e272b45380b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: autogenerate also proposed dropping ix_document_chunks_document_id,
    # ix_document_chunks_embedding_hnsw and ix_documents_domain_id — the same
    # known false positive as e272b45380b3 (see .claude/skills/db-migration/
    # SKILL.md): those indexes are created via raw op.execute()/
    # op.create_index() in 542eb8b7605b and aren't represented in SQLAlchemy
    # model metadata, so autogenerate's DB-vs-metadata diff mistakes them for
    # removed indexes. Intentionally not touching them here.
    op.create_table('chat_messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('domain_id', sa.UUID(), nullable=False),
    sa.Column('session_id', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('user', 'assistant')", name='ck_chat_messages_role'),
    sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chat_messages_domain_session_created', 'chat_messages', ['domain_id', 'session_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
    op.drop_index('ix_chat_messages_domain_session_created', table_name='chat_messages')
    op.drop_table('chat_messages')
