"""Where the count of a batch's outstanding downloads is kept.

Split from :mod:`bot.core.batches` for the reason every store here is split:
importing ``yt_shared.db.session`` builds the engine and drags in asyncpg.
"""

import datetime
from typing import Protocol

from yt_shared.db.session import get_db
from yt_shared.repositories.download_batch import DownloadBatchRepository


class BatchStore(Protocol):
    async def start(
        self,
        chat_id: int,
        message_id: int,
        count: int,
        summary_message_id: int | None,
    ) -> None: ...

    async def finish_one(
        self, chat_id: int, message_id: int
    ) -> tuple[int, int | None] | None: ...

    async def delete(self, chat_id: int, message_id: int) -> None: ...

    async def delete_older_than(self, cutoff: datetime.datetime) -> int: ...


class PostgresBatchStore:
    async def start(
        self,
        chat_id: int,
        message_id: int,
        count: int,
        summary_message_id: int | None,
    ) -> None:
        values = {
            'chat_id': chat_id,
            'message_id': message_id,
            'summary_message_id': summary_message_id,
            'remaining': count,
            'added_at': datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        }
        async for db in get_db():
            await DownloadBatchRepository(db).start(values)

    async def finish_one(
        self, chat_id: int, message_id: int
    ) -> tuple[int, int | None] | None:
        async for db in get_db():
            return await DownloadBatchRepository(db).finish_one(chat_id, message_id)
        return None

    async def delete(self, chat_id: int, message_id: int) -> None:
        async for db in get_db():
            await DownloadBatchRepository(db).delete(chat_id, message_id)

    async def delete_older_than(self, cutoff: datetime.datetime) -> int:
        async for db in get_db():
            return await DownloadBatchRepository(db).delete_older_than(cutoff)
        return 0
