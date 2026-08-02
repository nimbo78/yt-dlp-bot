"""Refusing a download that will not fit, rather than filling the disk with it.

Without this, running out of space is discovered when FFmpeg is already halfway
through merging: the download is wasted, the reason reaching the user is
whatever the failing tool happened to print, and the staging area is left full.

Two checks, because neither covers the other:

* a **floor**, before anything starts, for "the disk is already nearly full";
* a **per-download** check on the first progress tick, once yt-dlp knows how
  large the thing is, for "this particular video will not fit".

The second one runs inside a yt-dlp progress hook. Raising there aborts the
download, and because the worker runs yt-dlp with ``ignoreerrors`` the message
is collected by :class:`~worker.core.ytdlp_logger.YtdlpLogger` and travels the
same path as any other failure reason — so it reaches the user through the same
classifier that explains suspended accounts and private videos.
"""

import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from yt_shared.utils.common import format_bytes

# A download needs room for more than the finished file: video and audio arrive
# as separate streams and are then merged into a third. Three times the reported
# size is a rough figure, deliberately generous, because being wrong in the
# other direction is what this module exists to prevent.
_SIZE_MULTIPLIER: Final[float] = 3.0

_log = logging.getLogger(__name__)


class NotEnoughSpaceError(Exception):
    """Raised when a download cannot fit in the space that is left."""


def required_bytes(
    media_bytes: int, floor_bytes: int, multiplier: float = _SIZE_MULTIPLIER
) -> int:
    """How much free space a download of this size needs in order to finish."""
    return int(media_bytes * multiplier) + floor_bytes


def shortage_message(free: int, required: int) -> str:
    """Word the refusal so both the log and the error classifier recognise it."""
    return (
        f'Not enough free space: {format_bytes(free)} available, '
        f'about {format_bytes(required)} needed'
    )


def free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def ensure_floor(path: Path, floor_bytes: int) -> None:
    """Refuse before starting when the staging area is already low.

    Cheap, and it catches the case a per-download check cannot: a disk that is
    full before yt-dlp has been given the chance to report a size.
    """
    if floor_bytes <= 0:
        return
    free = free_bytes(path)
    if free < floor_bytes:
        message = shortage_message(free, floor_bytes)
        _log.error('%s (staging area %s)', message, path)
        raise NotEnoughSpaceError(message)


def make_space_guard(path: Path, floor_bytes: int) -> Callable[[dict[str, Any]], None]:
    """Build a yt-dlp progress hook that stops a download that will not fit.

    The check compares against ``free + downloaded``, not ``free`` alone: the
    bytes already written came out of the same free space, and counting them
    twice would abort a download that was going to fit after all.
    """

    def guard(status: dict[str, Any]) -> None:
        if status.get('status') != 'downloading':
            return
        total = status.get('total_bytes') or status.get('total_bytes_estimate')
        if not total:
            # Some sites never report a size. The floor is all we have then.
            return

        downloaded = status.get('downloaded_bytes') or 0
        available = free_bytes(path) + downloaded
        needed = required_bytes(int(total), floor_bytes)
        if available < needed:
            message = shortage_message(available, needed)
            _log.error('%s, stopping the download', message)
            raise NotEnoughSpaceError(message)

    return guard
