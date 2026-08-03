"""Turning a list of playlist entries into pages of buttons.

Two hard limits shape everything here, and neither announces itself when
exceeded — the button simply stops working:

* **Callback data is capped at 64 bytes.** Telegram rejects a longer one, and
  a keyboard built with it fails to send. Everything a press has to carry is
  therefore an index into stored state rather than the state itself: a URL of
  any length would blow the budget on its own.
* **A button label has no useful limit but plenty of practical ones.** A long
  title pushes the row into an unreadable wrap on a phone, so titles are cut
  here rather than left to the client.

Kept free of Pyrogram so it can be tested: the markup is assembled from what
this returns, in `bot.core.keyboards`.
"""

import datetime
from dataclasses import dataclass
from typing import Any, Final

# Prefixes for the callback data this builds. Short on purpose — every byte
# here is one not available to the identifier that follows.
PLAYLIST_PREFIX: Final[str] = 'pl:'
PLAYLIST_PAGE_PREFIX: Final[str] = 'pp:'
PLAYLIST_ITEM_PREFIX: Final[str] = 'pi:'
# The page counter is a button because a keyboard row has nothing else to put
# there. Its data matches no dispatch branch on purpose — the fallback in
# `on_callback_query` answers it, along with anything an older build drew.
PLAYLIST_NOOP: Final[str] = 'pnoop'

# Telegram's own limit, in bytes rather than characters.
CALLBACK_DATA_LIMIT: Final[int] = 64

# Enough to scan without scrolling past the message above it.
PAGE_SIZE: Final[int] = 8
# Angle quotes rather than < and >, which are markup wherever this travels.
PREVIOUS_LABEL: Final[str] = '\u2039'
NEXT_LABEL: Final[str] = '\u203a'
# Beyond this a title is not read, only stepped over.
LABEL_LIMIT: Final[int] = 32


@dataclass(frozen=True)
class MenuEntry:
    """One offerable item, as stored when the playlist was enumerated."""

    index: int
    title: str
    url: str


@dataclass(frozen=True)
class StoredPlaylist:
    """An enumeration as it comes back out of storage, age included.

    The age travels with it rather than being judged in the store: whether it
    is too old to offer is policy, and policy lives in `bot.core.playlists`
    where it can be tested without a database driver on the import path.
    """

    entries: list[MenuEntry]
    added_at: datetime.datetime


def entries_to_rows(entries: list[MenuEntry]) -> list[dict[str, Any]]:
    return [{'index': e.index, 'title': e.title, 'url': e.url} for e in entries]


def rows_to_entries(rows: Any) -> list[MenuEntry]:
    """Read stored rows back, skipping anything no longer usable.

    A row written by an earlier build can be missing a key, and a column that
    holds JSON can hold anything at all. One bad entry is not a reason to lose
    the whole menu, so it is dropped and the rest is still offered.
    """
    if not isinstance(rows, list):
        return []
    entries: list[MenuEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            entries.append(
                MenuEntry(
                    index=int(row['index']),
                    title=str(row['title']),
                    url=str(row['url']),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return entries


@dataclass(frozen=True)
class MenuButton:
    label: str
    data: str


@dataclass(frozen=True)
class MenuPage:
    """One screenful, ready to be turned into markup."""

    number: int
    total_pages: int
    rows: list[list[MenuButton]]
    # The entries actually shown, in order, for whoever wants to describe them.
    entries: list[MenuEntry]


def page_count(entry_count: int, page_size: int = PAGE_SIZE) -> int:
    """How many pages the entries fill. Always at least one, even for none."""
    if entry_count <= 0:
        return 1
    return (entry_count + page_size - 1) // page_size


def clamp_page(page: int, entry_count: int, page_size: int = PAGE_SIZE) -> int:
    """Bring a page number back into range.

    Pressing a page button on a menu that has since been re-enumerated shorter
    is the case this exists for: answering with the last page beats answering
    with an error about a page nobody chose deliberately.
    """
    return max(0, min(page, page_count(entry_count, page_size) - 1))


def truncate_label(title: str, limit: int = LABEL_LIMIT) -> str:
    """Cut a title to something that fits on a button.

    The ellipsis is a real character rather than three dots so that the cut is
    obvious at a glance and costs one column instead of three.
    """
    title = ' '.join(title.split())
    if len(title) <= limit:
        return title
    return f'{title[: limit - 1].rstrip()}…'


def entry_label(entry: MenuEntry, limit: int = LABEL_LIMIT) -> str:
    """Write the source number, then as much of the title as fits."""
    return f'{entry.index}. {truncate_label(entry.title, limit)}'


def build_menu(
    entries: list[MenuEntry],
    url_id: str,
    *,
    cancel_label: str,
    # Passed in rather than spelled here: the prefix belongs to `keyboards`,
    # which cannot be imported from this side without a cycle, and a literal
    # copy of it would survive a rename in silence.
    cancel_data: str,
    page: int = 0,
) -> MenuPage:
    """Lay out one page: an item per row, then navigation, then cancel.

    One button per row rather than two: these are titles, and two of them side
    by side leaves room for neither.
    """
    total_pages = page_count(len(entries))
    page = clamp_page(page, len(entries))
    shown = entries[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    rows: list[list[MenuButton]] = [
        [
            MenuButton(
                label=entry_label(entry),
                data=f'{PLAYLIST_ITEM_PREFIX}{url_id}:{entry.index}',
            )
        ]
        for entry in shown
    ]

    if total_pages > 1:
        rows.append([
            MenuButton(
                label=PREVIOUS_LABEL,
                # Wraps around, because the alternative is a dead button on the
                # first page and a menu that looks broken.
                data=f'{PLAYLIST_PAGE_PREFIX}{url_id}:{(page - 1) % total_pages}',
            ),
            MenuButton(label=f'{page + 1}/{total_pages}', data=PLAYLIST_NOOP),
            MenuButton(
                label=NEXT_LABEL,
                data=f'{PLAYLIST_PAGE_PREFIX}{url_id}:{(page + 1) % total_pages}',
            ),
        ])

    rows.append([MenuButton(label=cancel_label, data=cancel_data)])
    return MenuPage(
        number=page, total_pages=total_pages, rows=rows, entries=list(shown)
    )


def find_entry(entries: list[MenuEntry], index: int) -> MenuEntry | None:
    """Look an entry up by the number on its button.

    By source position, not by position in the list: unusable entries were
    dropped when the playlist was read and the numbering did not close up.
    """
    for entry in entries:
        if entry.index == index:
            return entry
    return None
