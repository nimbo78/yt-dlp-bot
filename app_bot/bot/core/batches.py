"""Knowing when the last download from one message has finished.

Every task believes it is alone, which is right for the single downloads that
are almost all of them. A playlist selection makes several from one message,
and two things then need somebody to be last: the message the links arrived in
must not be deleted while three more are still queued, and the "4 queued"
summary has nobody pointing at it and would sit on screen for good.

So the count lives here, and the task that takes it to zero does the tidying.
A download that belongs to no batch — every ordinary one — gets ``None`` back
and carries on exactly as before.
"""

import datetime
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from bot.core.batch_store import BatchStore

# Long enough that a queue of large downloads finishes inside it, short enough
# that a batch abandoned by a crash does not linger.
TTL: Final[datetime.timedelta] = datetime.timedelta(hours=12)


@dataclass(frozen=True)
class BatchProgress:
    """What is left of a batch after one of its downloads ended."""

    remaining: int
    summary_message_id: int | None

    @property
    def is_last(self) -> bool:
        """Whether this was the one that finished it.

        `<= 0` rather than `== 0`: a task delivered twice would otherwise take
        the count negative and nobody would ever be last.
        """
        return self.remaining <= 0


class Batches:
    def __init__(self, store: 'BatchStore') -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._store = store

    @staticmethod
    def _cutoff() -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - TTL

    async def start(
        self, chat_id: int, message_id: int, count: int, summary_message_id: int | None
    ) -> None:
        try:
            await self._store.start(chat_id, message_id, count, summary_message_id)
        except Exception:
            # Losing the record costs the tidying up, not the downloads. They
            # are already queued and will arrive either way.
            self._log.exception('Could not record a batch for message %s', message_id)

    async def finish_one(
        self, chat_id: int | None, message_id: int | None
    ) -> BatchProgress | None:
        """Count one download off, or answer ``None`` if it was not in a batch.

        Both ids are optional on the payloads this is called from — the API can
        queue a download that came from no message at all — and a batch is
        keyed by exactly those two, so without them there is nothing to look up.
        """
        if chat_id is None or message_id is None:
            return None
        try:
            found = await self._store.finish_one(chat_id, message_id)
        except Exception:
            # Unreadable means "not a batch", which is the old behaviour: the
            # source message goes and the summary stays. Wrong in a small way,
            # where raising here would break the delivery of a finished file.
            self._log.exception('Could not count off a batch for %s', message_id)
            return None

        if found is None:
            return None
        remaining, summary_message_id = found
        progress = BatchProgress(
            remaining=remaining, summary_message_id=summary_message_id
        )
        if progress.is_last:
            await self._forget(chat_id, message_id)
        return progress

    async def _forget(self, chat_id: int, message_id: int) -> None:
        try:
            await self._store.delete(chat_id, message_id)
        except Exception:
            self._log.exception('Could not drop the batch for %s', message_id)

    async def sweep(self) -> int:
        """Drop batches nothing ever finished, and say how many that was."""
        return await self._store.delete_older_than(self._cutoff())
