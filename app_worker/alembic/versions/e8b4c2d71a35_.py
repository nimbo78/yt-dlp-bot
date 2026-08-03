"""Remember which playlist entries are ticked.

Selecting several and downloading them at one quality means the ticks have to
outlive the press that made them, and the process that drew the keyboard.

Revision ID: e8b4c2d71a35
Revises: d7a3b1c96f80
Create Date: 2026-08-03 00:20:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'e8b4c2d71a35'
down_revision = 'd7a3b1c96f80'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: a menu drawn before this migration has no answer, and an empty
    # list is a different statement from "never asked".
    op.add_column('playlist', sa.Column('selected', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('playlist', 'selected')
