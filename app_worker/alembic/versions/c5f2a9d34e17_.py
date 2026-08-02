"""Keep pending format choices outside the bot process.

They lived in a dict, so every restart orphaned the keyboards already on screen
and pressing one answered "this request has expired".

Revision ID: c5f2a9d34e17
Revises: b3d81f5c6e04
Create Date: 2026-08-02 22:55:00.000000

"""

import sqlalchemy as sa
from sqlalchemy_utils import UUIDType

from alembic import op

# revision identifiers, used by Alembic.
revision = 'c5f2a9d34e17'
down_revision = 'b3d81f5c6e04'
branch_labels = None
depends_on = None

_CHAT_TYPE = sa.Enum(
    'PRIVATE', 'BOT', 'GROUP', 'SUPERGROUP', 'CHANNEL', name='telegramchattype'
)


def upgrade() -> None:
    _CHAT_TYPE.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'pending_download',
        sa.Column('id', UUIDType(binary=False), nullable=False),
        sa.Column('url_id', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('original_url', sa.String(), nullable=False),
        sa.Column('from_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('from_chat_type', _CHAT_TYPE, nullable=False),
        sa.Column('from_user_id', sa.BigInteger(), nullable=True),
        sa.Column('message_id', sa.BigInteger(), nullable=False),
        sa.Column('ack_message_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('save_to_storage', sa.Boolean(), nullable=False),
        sa.Column('skip_cache', sa.Boolean(), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('updated', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'pending_download_url_id_idx', 'pending_download', ['url_id'], unique=True
    )
    op.create_index(
        'pending_download_added_at_idx', 'pending_download', ['added_at']
    )


def downgrade() -> None:
    op.drop_index('pending_download_added_at_idx', table_name='pending_download')
    op.drop_index('pending_download_url_id_idx', table_name='pending_download')
    op.drop_table('pending_download')
