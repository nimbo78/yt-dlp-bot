"""Links waiting for someone to choose a format for them.

A pasted link becomes a keyboard, and the choice behind it has to be kept
somewhere until a button is pressed. Most are pressed within seconds; the ones
that are not would otherwise stay here for the life of the process, which on a
bot that runs for months is a slow leak.

Entries therefore expire. This does **not** make them survive a restart — the
store lives in the process, so `/restartbot` still orphans every keyboard on
screen. Pressing one of those answers "this request has expired", which is
exactly what happened.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import ClassVar, Final

from yt_shared.enums import TelegramChatType

from bot.core.schemas import UserSchema

# A keyboard nobody has touched in two days is not going to be touched.
_TTL_SECONDS: Final[float] = 48 * 60 * 60


@dataclass
class PendingDownload:
    """Pending download request data."""

    url: str
    original_url: str
    from_chat_id: int
    from_chat_type: TelegramChatType
    from_user_id: int | None
    message_id: int
    ack_message_id: int
    save_to_storage: bool
    user: UserSchema
    # Monotonic on purpose: a clock correction must not make an entry immortal
    # or expire every one of them at once.
    added_at: float = field(default_factory=time.monotonic)

    def is_expired(self, ttl: float, now: float) -> bool:
        return now - self.added_at >= ttl


class PendingDownloadsStore:
    """In-memory store for pending download requests.

    Uses a simple dict with url_id as key. URL ID is generated from
    message_id and chat_id to ensure uniqueness.
    """

    TTL_SECONDS: ClassVar[float] = _TTL_SECONDS

    _store: ClassVar[dict[str, PendingDownload]] = {}
    _log = logging.getLogger('PendingDownloadsStore')

    @classmethod
    def generate_url_id(cls, chat_id: int, message_id: int) -> str:
        """Generate unique URL ID from chat and message IDs."""
        return f'{chat_id}_{message_id}'

    @classmethod
    def add(cls, url_id: str, pending: PendingDownload) -> None:
        """Add pending download to store."""
        cls._log.debug('Adding pending download: %s', url_id)
        cls._store[url_id] = pending

    @classmethod
    def get(cls, url_id: str) -> PendingDownload | None:
        """Get pending download by URL ID, unless it has expired."""
        return cls._take(url_id, keep=True)

    @classmethod
    def remove(cls, url_id: str) -> PendingDownload | None:
        """Remove and return pending download by URL ID."""
        cls._log.debug('Removing pending download: %s', url_id)
        return cls._take(url_id, keep=False)

    @classmethod
    def _take(cls, url_id: str, *, keep: bool) -> PendingDownload | None:
        """Look an entry up, dropping it if it is too old to honour."""
        pending = cls._store.get(url_id)
        if pending is None:
            return None
        if pending.is_expired(cls.TTL_SECONDS, time.monotonic()):
            # Evicting on access alone would never reach an entry nobody comes
            # back to, which is why the sweep below exists as well.
            cls._log.debug('Pending download %s has expired', url_id)
            cls._store.pop(url_id, None)
            return None
        if not keep:
            cls._store.pop(url_id, None)
        return pending

    @classmethod
    def sweep(cls) -> int:
        """Drop every entry past its time, and say how many that was."""
        now = time.monotonic()
        expired = [
            url_id
            for url_id, pending in cls._store.items()
            if pending.is_expired(cls.TTL_SECONDS, now)
        ]
        for url_id in expired:
            del cls._store[url_id]
        return len(expired)

    @classmethod
    def size(cls) -> int:
        return len(cls._store)

    @classmethod
    def clear(cls) -> None:
        """Clear all pending downloads."""
        cls._store.clear()
