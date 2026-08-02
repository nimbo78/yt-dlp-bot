"""Record what was asked for, so a repeat can be served from the file cache.

Telegram file ids were already stored on every upload but nothing could look one
up: the url was recorded, the media type and quality were not, and a file row
did not say whether it held audio or video. Without those three a repeat request
cannot be matched to the right cached file — the same link at 1080p and at 720p
are different answers.

Revision ID: b3d81f5c6e04
Revises: a1c7e4b90f22
Create Date: 2026-08-02 22:10:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'b3d81f5c6e04'
down_revision = 'a1c7e4b90f22'
branch_labels = None
depends_on = None

_MEDIA_FILE_TYPE = sa.Enum('AUDIO', 'VIDEO', name='mediafiletype')
_DOWN_MEDIA_TYPE = sa.Enum('AUDIO', 'VIDEO', 'AUDIO_VIDEO', name='downmediatype')
_VIDEO_QUALITY = sa.Enum(
    'BEST', 'UHD_4K', 'QHD_1440P', 'FHD_1080P', 'HD_720P', 'SD_480P', 'LD_360P',
    name='videoquality',
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (_MEDIA_FILE_TYPE, _DOWN_MEDIA_TYPE, _VIDEO_QUALITY):
        enum.create(bind, checkfirst=True)

    # Nullable throughout: rows written before this migration have no answer,
    # and guessing one would hand somebody the wrong file.
    op.add_column(
        'task', sa.Column('download_media_type', _DOWN_MEDIA_TYPE, nullable=True)
    )
    op.add_column('task', sa.Column('video_quality', _VIDEO_QUALITY, nullable=True))
    op.add_column('file', sa.Column('file_type', _MEDIA_FILE_TYPE, nullable=True))
    op.create_index('task_cache_lookup_idx', 'task', ['url', 'download_media_type'])


def downgrade() -> None:
    op.drop_index('task_cache_lookup_idx', table_name='task')
    op.drop_column('file', 'file_type')
    op.drop_column('task', 'video_quality')
    op.drop_column('task', 'download_media_type')
    bind = op.get_bind()
    for enum in (_MEDIA_FILE_TYPE, _DOWN_MEDIA_TYPE, _VIDEO_QUALITY):
        enum.drop(bind, checkfirst=True)
