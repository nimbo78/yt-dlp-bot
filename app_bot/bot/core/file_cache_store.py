"""Where the bot asks whether Telegram already holds a file.

Split from the delivery logic for the same reason the startup store is:
``yt_shared.db.session`` builds the database engine at import time and pulls in
asyncpg, so keeping it out of the module that decides *what to send* keeps that
decision testable without a database driver on the path.
"""

from typing import Protocol

from yt_shared.db.session import get_db
from yt_shared.enums import DownMediaType, VideoQuality
from yt_shared.repositories.task import TaskRepository
from yt_shared.schemas.file_cache import CachedFile


class FileCacheStore(Protocol):
    async def find(
        self,
        url: str,
        download_media_type: DownMediaType,
        video_quality: VideoQuality,
    ) -> list[CachedFile]: ...


class PostgresFileCacheStore:
    async def find(
        self,
        url: str,
        download_media_type: DownMediaType,
        video_quality: VideoQuality,
    ) -> list[CachedFile]:
        async for db in get_db():
            return await TaskRepository(db).find_cached_files(
                url=url,
                download_media_type=download_media_type,
                video_quality=video_quality,
            )
        return []
