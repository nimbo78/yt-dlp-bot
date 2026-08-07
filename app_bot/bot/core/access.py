"""Who is allowed to talk to the bot, asked fresh every time.

The lists used to be read once, when the handlers were registered, and frozen
into Pyrogram's `filters.user(...)`. `/adduser` writes the config, reloads it
and updates the bot's own dictionaries — but the filter still held the list from
startup, so the new user's messages were dropped and the command reported
success anyway. The only way to actually let somebody in was `/restartbot`.

The decision is a set membership, kept here as a plain function so it can be
tested; extracting the ids from a Pyrogram update needs Pyrogram and lives in
`bot.core.filters` next door.
"""

from collections.abc import Iterable


def is_known(candidates: Iterable[int | None], known: Iterable[int]) -> bool:
    """Whether any of these ids is one we recognise.

    Several are offered because a group is configured under its chat id while
    the person writing has one of their own, and either may be the one listed.
    ``None`` appears for a message with no sender, such as one from a channel.
    """
    known_ids = set(known)
    return any(
        candidate is not None and candidate in known_ids for candidate in candidates
    )
