"""Links waiting for someone to choose a format for them.

A pasted link becomes a keyboard, and the choice behind it has to be kept until
a button is pressed. That used to be a dict in the bot process, which meant two
things: it grew forever, and every restart orphaned the keyboards already on
screen — pressing one answered "this request has expired" when nothing had.

Both are now handled. Entries live outside the process and expire after two
days, on access and by a periodic sweep, because eviction on access alone never
reaches an entry nobody comes back to.

The user is referenced by id rather than carried along: their settings can
change while a keyboard waits, and the configuration is the authority on what
they are now. A user removed from it in the meantime makes the entry unusable,
which is the right answer.
"""

import datetime
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from yt_shared.enums import TelegramChatType

from bot.core.schemas import UserSchema

if TYPE_CHECKING:
    from bot.core.pending_download_store import PendingDownloadStore

# A keyboard nobody has touched in two days is not going to be touched.
TTL: Final[datetime.timedelta] = datetime.timedelta(hours=48)


@dataclass
class PendingDownload:
    """A link and everything needed to act on it once a format is chosen."""

    url: str
    original_url: str
    from_chat_id: int
    from_chat_type: TelegramChatType
    from_user_id: int | None
    message_id: int
    ack_message_id: int
    save_to_storage: bool
    user: UserSchema
    # Set by /nocache, for when the stored copy is wrong or stale.
    skip_cache: bool = False
    # Filled in when a choice is read back; unset on a freshly made one.
    added_at: datetime.datetime | None = None

    def is_expired(self, cutoff: datetime.datetime) -> bool:
        """Whether this is too old to honour. An unknown age counts as fresh."""
        return self.added_at is not None and self.added_at < cutoff


def generate_url_id(chat_id: int, message_id: int) -> str:
    """Name a pending choice after the message that started it."""
    return f'{chat_id}_{message_id}'


class PendingDownloads:
    """Reads and writes pending choices, dropping the ones that are too old."""

    def __init__(self, store: 'PendingDownloadStore') -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._store = store

    @staticmethod
    def _cutoff() -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - TTL

    async def add(self, url_id: str, pending: PendingDownload) -> None:
        self._log.debug('Adding pending download: %s', url_id)
        await self._store.save(url_id, pending)

    async def get(self, url_id: str) -> PendingDownload | None:
        """Look a choice up, unless it is too old to honour."""
        return await self._take(url_id, keep=True)

    async def remove(self, url_id: str) -> PendingDownload | None:
        """Take a choice, so that acting on it twice is not possible."""
        self._log.debug('Removing pending download: %s', url_id)
        return await self._take(url_id, keep=False)

    async def _take(self, url_id: str, *, keep: bool) -> PendingDownload | None:
        try:
            found = await self._store.load(url_id)
        except Exception:
            # A store that cannot be read looks like an expired request, which
            # is a great deal better than a traceback in front of the user.
            self._log.exception('Could not read the pending download %s', url_id)
            return None

        if found is None:
            return None
        if found.is_expired(self._cutoff()):
            # Evicting on access alone would never reach an entry nobody comes
            # back to, which is why the sweep exists as well.
            self._log.debug('Pending download %s has expired', url_id)
            await self._store.delete(url_id)
            return None
        if not keep:
            await self._store.delete(url_id)
        return found

    async def sweep(self) -> int:
        """Drop every choice past its time, and say how many that was."""
        return await self._store.delete_older_than(self._cutoff())

    async def size(self) -> int:
        return await self._store.count()
