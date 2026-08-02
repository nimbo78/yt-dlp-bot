import uuid
from datetime import datetime
from typing import Any, ClassVar

import sqlalchemy as sa
from sqlalchemy import Index, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, validates
from sqlalchemy_utils import Timestamp, UUIDType

from yt_shared.db.session import Base
from yt_shared.enums import (
    DownMediaType,
    MediaFileType,
    TaskSource,
    TaskStatus,
    VideoQuality,
)
from yt_shared.models.yt_dlp import YTDLP


class Task(Base, Timestamp):
    id = sa.Column(UUIDType(binary=False), primary_key=True, default=uuid.uuid4)
    status = sa.Column(
        sa.Enum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING.name,
        server_default=TaskStatus.PENDING.name,
        index=True,
    )
    url = sa.Column(sa.String, nullable=False)
    source = sa.Column(sa.Enum(TaskSource), nullable=False, index=True)
    # What was asked for. Needed to match a repeat request to a cached file:
    # the same link at 1080p and at 720p are different answers. Nullable
    # because rows written before this existed cannot be given one.
    download_media_type = sa.Column(sa.Enum(DownMediaType), nullable=True)
    video_quality = sa.Column(sa.Enum(VideoQuality), nullable=True)
    files = relationship('File', backref='task', cascade='all, delete-orphan')
    added_at = sa.Column(sa.DateTime, nullable=False)
    from_user_id = sa.Column(sa.BigInteger, nullable=True)
    message_id = sa.Column(sa.BigInteger, nullable=True)
    error = sa.Column(sa.String, nullable=True)
    yt_dlp_version = sa.Column(
        sa.String, nullable=True, default=select(YTDLP.current_version)
    )

    @validates('added_at')
    def validate_added_at(self, key: str, added_at: datetime) -> datetime:  # noqa: ARG002
        """Remove UTC timezone from aware datetime before saving."""
        return added_at.replace(tzinfo=None)

    # Fetch the value of server-generated default values like 'yt_dlp_version'.
    __mapper_args__: ClassVar[dict[str, Any]] = {'eager_defaults': True}


task_created_at_index = Index('task_created_at_idx', Task.created)
task_cache_lookup_index = Index(
    'task_cache_lookup_idx', Task.url, Task.download_media_type
)


class File(Base, Timestamp):
    id = sa.Column(UUIDType(binary=False), primary_key=True, default=uuid.uuid4)
    file_type = sa.Column(sa.Enum(MediaFileType), nullable=True)
    title = sa.Column(sa.String, nullable=True)
    name = sa.Column(sa.String, nullable=True)
    thumb_name = sa.Column(sa.String, nullable=True)
    duration = sa.Column(sa.Integer, nullable=True)
    width = sa.Column(sa.Integer, nullable=True)
    height = sa.Column(sa.Integer, nullable=True)
    meta = sa.Column(JSONB, nullable=True)
    task_id = sa.Column(
        UUIDType(binary=False),
        sa.ForeignKey('task.id', ondelete='CASCADE'),
        nullable=False,
        unique=False,
        index=True,
    )
    cache = relationship(
        'Cache', backref='file', uselist=False, cascade='all, delete-orphan'
    )
