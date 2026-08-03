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

from dataclasses import dataclass
from typing import Any, Final

from yt_shared.schemas.playlist import MAX_PLAYLIST_ENTRIES, PlaylistEntryPayload

# yt-dlp writes these in the title when it could not read the entry itself.
_UNREADABLE_TITLES: Final[frozenset[str]] = frozenset({
    '[deleted video]',
    '[private video]',
    '[unavailable]',
})


@dataclass(frozen=True)
class Playlist:
    title: str
    entries: list[PlaylistEntryPayload]
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


def entries_from_info(
    info: dict[str, Any], limit: int = MAX_PLAYLIST_ENTRIES
) -> Playlist:
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

    entries: list[PlaylistEntryPayload] = []
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
        entries.append(
            PlaylistEntryPayload(index=position, title=title, url=url)
        )

    return Playlist(title=_playlist_title(info), entries=entries, total=len(raw))


def _playlist_title(info: dict[str, Any]) -> str:
    title = info.get('title')
    if isinstance(title, str) and title.strip():
        return title.strip()
    return 'Playlist'


def apply_flat_overrides(
    opts: dict[str, Any], limit: int, *, cookies_last_resort: bool
) -> dict[str, Any]:
    """Force what the download options must not be allowed to decide here.

    Kept as a plain dict-in, dict-out function so it can be tested without
    yt-dlp: what it corrects is exactly what is invisible until somebody opens
    a menu and finds one item in it.

    `--playlist-items 1:1` is in the shipped defaults, and in yt-dlp that
    setting *wins over* `--playlist-end` — `PlaylistEntries` only falls back to
    the start/end pair when `playlist_items` is unset. Inheriting it would cap
    every enumeration at the first entry, and nothing would say so: the menu
    would simply show one row. `--no-playlist` is in there for the same reason
    and has to go the same way.
    """
    opts = dict(opts)
    opts['noplaylist'] = False
    opts['playlist_items'] = f'1:{limit}'
    # An output template is meaningless when nothing is written.
    opts.pop('outtmpl', None)
    if cookies_last_resort:
        # This host is happier anonymously — an authenticated session from a
        # server address is what draws the bot check. The download path tries
        # without the cookies first, and so does this.
        opts.pop('cookiefile', None)
    return opts
