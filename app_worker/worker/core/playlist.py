"""Turning what yt-dlp says about a playlist into something offerable.

Enumerating is cheap — ``extract_flat`` asks for the index page and stops, with
no per-item requests and nothing downloaded — but what comes back is loose.
Entries can be ``None`` where an item is private or deleted, a title can be
missing or be the placeholder yt-dlp uses for one it could not read, and the URL
lives under different keys depending on the extractor. A single-item link
extracts as a plain video with no ``entries`` at all.

So the parsing is separated from the fetching: this module is handed a dict and
returns entries, which means every one of those shapes is a test rather than
something discovered in production.
"""

import logging
from dataclasses import dataclass
from typing import Any, Final

_log = logging.getLogger(__name__)

# What the bot can reasonably show and a small host can reasonably enumerate.
# A channel with ten thousand videos is not a menu.
MAX_ENTRIES: Final[int] = 100

# yt-dlp writes these in the title when it could not read the entry itself.
_UNREADABLE_TITLES: Final[frozenset[str]] = frozenset({
    '[deleted video]',
    '[private video]',
    '[unavailable]',
})


@dataclass(frozen=True)
class PlaylistEntry:
    """One offerable item: a link, and something to write on the button."""

    index: int
    title: str
    url: str


@dataclass(frozen=True)
class Playlist:
    title: str
    entries: list[PlaylistEntry]
    # How many the source claimed, before the limit and the skipping. Shown so
    # "10 of 250" is not silently rendered as "10".
    total: int

    @property
    def is_truncated(self) -> bool:
        return self.total > len(self.entries)


def _entry_url(entry: dict[str, Any]) -> str | None:
    """Find the link to hand back, or ``None`` when there is nothing usable.

    Extractors disagree on where it lives, and a flat extraction sometimes
    yields a bare id rather than an address. A bare id is not resolvable
    without knowing the extractor, so it is treated as missing: offering a
    button that cannot work is worse than offering one fewer.
    """
    for key in ('url', 'webpage_url', 'original_url'):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith(('http://', 'https://')):
            return value
    return None


def _entry_title(entry: dict[str, Any], index: int) -> str | None:
    title = entry.get('title')
    if not isinstance(title, str) or not title.strip():
        # No title is not a reason to drop a playable item.
        return f'#{index}'
    if title.strip().lower() in _UNREADABLE_TITLES:
        return None
    return title.strip()


def entries_from_info(info: dict[str, Any], limit: int = MAX_ENTRIES) -> Playlist:
    """Read a flat extraction into an offerable list.

    Anything unusable is skipped rather than raised over: one dead item in a
    playlist of forty is not a failed request, and the count keeps the answer
    honest about it.
    """
    raw = info.get('entries')
    if not isinstance(raw, list):
        # A single video extracts with no `entries` at all. Not an error — the
        # caller decides what to do with an empty playlist.
        return Playlist(title=_playlist_title(info), entries=[], total=0)

    entries: list[PlaylistEntry] = []
    for position, entry in enumerate(raw, start=1):
        if len(entries) >= limit:
            break
        if not isinstance(entry, dict):
            # yt-dlp puts None here for an item it could not read at all.
            continue
        url = _entry_url(entry)
        if url is None:
            continue
        title = _entry_title(entry, position)
        if title is None:
            continue
        entries.append(PlaylistEntry(index=position, title=title, url=url))

    return Playlist(title=_playlist_title(info), entries=entries, total=len(raw))


def _playlist_title(info: dict[str, Any]) -> str:
    title = info.get('title')
    if isinstance(title, str) and title.strip():
        return title.strip()
    return 'Playlist'
