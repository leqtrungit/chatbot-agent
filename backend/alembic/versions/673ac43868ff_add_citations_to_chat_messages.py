"""add citations to chat_messages

Revision ID: 673ac43868ff
Revises: 50f7ec41ac19
Create Date: 2026-08-12 22:31:49.231677

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '673ac43868ff'
down_revision: Union[str, Sequence[str], None] = '50f7ec41ac19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chat_messages', sa.Column('citations', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_messages', 'citations')
