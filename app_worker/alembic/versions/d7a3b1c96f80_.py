"""Keep what a playlist turned out to contain while its menu is open.

Turning a page must not mean asking the site again, and a restart must not
orphan a menu already on screen.

Revision ID: d7a3b1c96f80
Revises: c5f2a9d34e17
Create Date: 2026-08-02 23:40:00.000000

"""

import sqlalchemy as sa
from sqlalchemy_utils import UUIDType

from alembic import op

# revision identifiers, used by Alembic.
revision = 'd7a3b1c96f80'
down_revision = 'c5f2a9d34e17'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'playlist',
        sa.Column('id', UUIDType(binary=False), nullable=False),
        sa.Column('url_id', sa.String(), nullable=False),
        sa.Column('entries', sa.JSON(), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('updated', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('playlist_url_id_idx', 'playlist', ['url_id'], unique=True)
    op.create_index('playlist_added_at_idx', 'playlist', ['added_at'])


def downgrade() -> None:
    op.drop_index('playlist_added_at_idx', table_name='playlist')
    op.drop_index('playlist_url_id_idx', table_name='playlist')
    op.drop_table('playlist')
