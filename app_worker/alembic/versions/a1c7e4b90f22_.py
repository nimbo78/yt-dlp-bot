"""Record the startup messages the bot posts, so it can remove them again.

Revision ID: a1c7e4b90f22
Revises: 50331b3c39bb
Create Date: 2026-08-02 21:40:00.000000

"""

import sqlalchemy as sa
from sqlalchemy_utils import UUIDType

from alembic import op

# revision identifiers, used by Alembic.
revision = 'a1c7e4b90f22'
down_revision = '50331b3c39bb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'startup_message',
        sa.Column('id', UUIDType(binary=False), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.BigInteger(), nullable=False),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('updated', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('startup_message')
