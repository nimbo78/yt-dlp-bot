"""Count the downloads that came from one message.

Without this every task believed it was alone, so the first item of a playlist
selection to finish deleted the message the link arrived in while three more
were still queued, and the "4 queued" summary stayed on screen for good.

Revision ID: f1c7a93b2e60
Revises: e8b4c2d71a35
Create Date: 2026-08-03 00:55:00.000000

"""

import sqlalchemy as sa
from sqlalchemy_utils import UUIDType

from alembic import op

# revision identifiers, used by Alembic.
revision = 'f1c7a93b2e60'
down_revision = 'e8b4c2d71a35'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'download_batch',
        sa.Column('id', UUIDType(binary=False), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.BigInteger(), nullable=False),
        sa.Column('summary_message_id', sa.BigInteger(), nullable=True),
        sa.Column('remaining', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('updated', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chat_id', 'message_id', name='download_batch_source_idx'),
    )
    op.create_index('download_batch_added_at_idx', 'download_batch', ['added_at'])


def downgrade() -> None:
    op.drop_index('download_batch_added_at_idx', table_name='download_batch')
    op.drop_table('download_batch')
