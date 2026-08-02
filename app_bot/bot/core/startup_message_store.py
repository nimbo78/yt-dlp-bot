"""Where the ids of posted startup messages are kept between runs.

Separate from :mod:`bot.core.startup_notice` on purpose. The notice is about
what to say and when to take it back; this is about surviving a restart, which
is the only reason a database is involved at all. Keeping them apart also keeps
the messaging logic testable without a database driver on the path.
"""

from typing import Protocol

from yt_shared.db.session import get_db
from yt_shared.repositories.startup_message import StartupMessageRepository

# (chat id, message id)
PostedMessage = tuple[int, int]


class StartupMessageStore(Protocol):
    """What the startup notice needs from persistence, and nothing more."""

    async def take_all(self) -> list[PostedMessage]:
        """Return everything recorded and forget it in the same breath."""
        ...

    async def save_all(self, messages: list[PostedMessage]) -> None: ...


class PostgresStartupMessageStore:
    """The real one. Postgres because the bot already talks to it.

    A file would not do: nothing under ``/app`` outlives the container, and
    ``redeploy.sh`` recreates it — which is exactly the case this has to
    survive.
    """

    async def take_all(self) -> list[PostedMessage]:
        async for db in get_db():
            return await StartupMessageRepository(db).take_all()
        return []

    async def save_all(self, messages: list[PostedMessage]) -> None:
        async for db in get_db():
            await StartupMessageRepository(db).save_all(messages)
