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
# Toggling one entry. Named "item" because that is what it was before the
# checkboxes; pressing it no longer downloads, it ticks.
PLAYLIST_ITEM_PREFIX: Final[str] = 'pi:'
# Select or clear the lot. The trailing flag is 1 or 0.
PLAYLIST_ALL_PREFIX: Final[str] = 'pa:'
# Done choosing — on to the format and the quality.
PLAYLIST_NEXT_PREFIX: Final[str] = 'pn:'
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
# Beyond this a title is not read, only stepped over. Two columns narrower
# than before, because a tick now sits in front of it.
LABEL_LIMIT: Final[int] = 30

# One download at a time is bounded by MAX_SIMULTANEOUS_DOWNLOADS, but the
# queue is not: selecting a whole channel would fill the staging area and take
# a day, with no way to stop it. A cap keeps a slip of the finger cheap.
MAX_SELECTED: Final[int] = 25

TICKED: Final[str] = '\u2611'
UNTICKED: Final[str] = '\u2610'


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
    # Which of them are ticked. Kept with the menu rather than in the process,
    # for the same reason the menu is: a restart must not lose it.
    selected: frozenset[int] = frozenset()


def entries_to_rows(entries: list[MenuEntry]) -> list[dict[str, Any]]:
    return [{'index': e.index, 'title': e.title, 'url': e.url} for e in entries]


def selection_to_rows(selected: frozenset[int]) -> list[int]:
    """Store the ticks in a stable order, so a row does not churn on rewrite."""
    return sorted(selected)


def rows_to_selection(rows: Any) -> frozenset[int]:
    """Read the ticks back, ignoring anything that is not a number."""
    if not isinstance(rows, list):
        return frozenset()
    numbers = set()
    for row in rows:
        try:
            numbers.add(int(row))
        except (TypeError, ValueError):
            continue
    return frozenset(numbers)


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
class MenuLabels:
    """The words on the buttons, already translated.

    Passed in as a bundle so this module needs no opinion about language and
    the caller needs no opinion about layout.
    """

    cancel: str
    select_all: str
    clear_all: str
    # Carries a `{count}` placeholder.
    next_step: str


@dataclass(frozen=True)
class MenuPage:
    """One screenful, ready to be turned into markup."""

    number: int
    total_pages: int
    rows: list[list[MenuButton]]
    # The entries actually shown, in order, for whoever wants to describe them.
    entries: list[MenuEntry]
    selected: frozenset[int] = frozenset()


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


def entry_label(
    entry: MenuEntry, *, selected: bool = False, limit: int = LABEL_LIMIT
) -> str:
    """Show whether it is ticked, its source number, and as much title as fits."""
    box = TICKED if selected else UNTICKED
    return f'{box} {entry.index}. {truncate_label(entry.title, limit)}'


def toggle(selected: frozenset[int], index: int) -> frozenset[int]:
    """Tick or untick one entry, refusing to go past the cap.

    Returning the set unchanged when full is what lets the caller tell the
    difference and say so, rather than silently dropping the press.
    """
    if index in selected:
        return selected - {index}
    if len(selected) >= MAX_SELECTED:
        return selected
    return selected | {index}


def select_all(entries: list[MenuEntry]) -> frozenset[int]:
    """Tick everything that fits, in source order.

    Truncating rather than refusing: somebody who presses this on a 100-entry
    playlist wants as much as they can have, and the header says how many.
    """
    return frozenset(e.index for e in entries[:MAX_SELECTED])


def selected_entries(
    entries: list[MenuEntry], selected: frozenset[int]
) -> list[MenuEntry]:
    """Collect the ticked entries, in the order the playlist has them.

    Order matters: these are queued one after another, and a set has none.
    """
    return [e for e in entries if e.index in selected]


def build_menu(  # noqa: PLR0913
    entries: list[MenuEntry],
    url_id: str,
    *,
    labels: 'MenuLabels',
    # Passed in rather than spelled here: the cancel prefix belongs to
    # `keyboards`, which cannot be imported from this side without a cycle, and
    # a literal copy of it would survive a rename in silence.
    cancel_data: str,
    page: int = 0,
    selected: frozenset[int] = frozenset(),
) -> MenuPage:
    """Lay out one page: the entries, navigation, the bulk actions, then done.

    One entry per row rather than two: these are titles, and two of them side
    by side leaves room for neither.
    """
    total_pages = page_count(len(entries))
    page = clamp_page(page, len(entries))
    shown = entries[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    rows: list[list[MenuButton]] = [
        [
            MenuButton(
                label=entry_label(entry, selected=entry.index in selected),
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

    if entries:
        rows.append([
            MenuButton(
                label=labels.select_all,
                data=f'{PLAYLIST_ALL_PREFIX}{url_id}:1',
            ),
            MenuButton(
                label=labels.clear_all,
                data=f'{PLAYLIST_ALL_PREFIX}{url_id}:0',
            ),
        ])

    if selected:
        # Only once something is ticked. An always-present "next" that answers
        # "nothing selected" is a button that lies about being available.
        rows.append([
            MenuButton(
                label=labels.next_step.format(count=len(selected)),
                data=f'{PLAYLIST_NEXT_PREFIX}{url_id}',
            )
        ])

    rows.append([MenuButton(label=labels.cancel, data=cancel_data)])
    return MenuPage(
        number=page,
        total_pages=total_pages,
        rows=rows,
        entries=list(shown),
        selected=selected,
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
