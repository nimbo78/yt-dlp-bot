"""Where pending format choices are kept between restarts.

Postgres rather than Redis. Redis is already running for the API, and its TTL
would have come for free, but the bot does not depend on a Redis client and
adding one means relocking `app_bot`, which would break the image build until
the lock is regenerated. Postgres costs a migration and nothing else — and its
volume is the one that already survives `docker compose down`.

Split from :mod:`bot.core.pending_downloads` for the usual reason: importing
``yt_shared.db.session`` builds the engine and pulls in asyncpg, and the expiry
rules are worth testing without a database driver on the path.
"""

import datetime
from typing import TYPE_CHECKING, Protocol

from yt_shared.db.session import get_db
from yt_shared.enums import TelegramChatType
from yt_shared.repositories.pending_download import PendingDownloadRepository

from bot.core.pending_downloads import PendingDownload

if TYPE_CHECKING:
    from bot.bot.client import VideoBotClient


class PendingDownloadStore(Protocol):
    async def save(self, url_id: str, pending: PendingDownload) -> None: ...

    async def load(self, url_id: str) -> PendingDownload | None: ...

    async def delete(self, url_id: str) -> None: ...

    async def delete_older_than(self, cutoff: datetime.datetime) -> int: ...

    async def count(self) -> int: ...


class PostgresPendingDownloadStore:
    def __init__(self, bot: 'VideoBotClient') -> None:
        # The bot is the authority on who a user is *now*, which is why only
        # their id is stored: settings may change while a keyboard waits.
        self._bot = bot

    async def save(self, url_id: str, pending: PendingDownload) -> None:
        values = {
            'url_id': url_id,
            'url': pending.url,
            'original_url': pending.original_url,
            'from_chat_id': pending.from_chat_id,
            'from_chat_type': pending.from_chat_type,
            'from_user_id': pending.from_user_id,
            'message_id': pending.message_id,
            'ack_message_id': pending.ack_message_id,
            'user_id': pending.user.id,
            'save_to_storage': pending.save_to_storage,
            'skip_cache': pending.skip_cache,
            'added_at': datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        }
        async for db in get_db():
            await PendingDownloadRepository(db).save(values)

    async def load(self, url_id: str) -> PendingDownload | None:
        async for db in get_db():
            row = await PendingDownloadRepository(db).get(url_id)
            if row is None:
                return None
            user = self._bot.allowed_users.get(row.user_id)
            if user is None:
                # Removed from the configuration while the keyboard waited.
                await PendingDownloadRepository(db).delete(url_id)
                return None
            return PendingDownload(
                url=row.url,
                original_url=row.original_url,
                from_chat_id=row.from_chat_id,
                from_chat_type=TelegramChatType(row.from_chat_type),
                from_user_id=row.from_user_id,
                message_id=row.message_id,
                ack_message_id=row.ack_message_id,
                save_to_storage=row.save_to_storage,
                user=user,
                skip_cache=row.skip_cache,
                added_at=row.added_at,
            )
        return None

    async def delete(self, url_id: str) -> None:
        async for db in get_db():
            await PendingDownloadRepository(db).delete(url_id)

    async def delete_older_than(self, cutoff: datetime.datetime) -> int:
        async for db in get_db():
            return await PendingDownloadRepository(db).delete_older_than(cutoff)
        return 0

    async def count(self) -> int:
        async for db in get_db():
            return await PendingDownloadRepository(db).count()
        return 0
