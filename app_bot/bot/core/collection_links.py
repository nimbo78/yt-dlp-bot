"""Telling a link to one thing apart from a link to a great many.

The worker runs yt-dlp with ``--no-playlist --playlist-items 1:1``
(``app_worker/ytdl_opts/default.py``), so a link to a playlist, an album or a
channel produces exactly one file and says nothing about the rest. That is the
worst shape a wrong answer can take: it looks like a success. Somebody who
pastes a 40-track album and gets one track back has no way to tell whether the
album had one track or the bot quietly dropped 39.

This does not add playlist support — downloading everything behind such a link
is a different feature, and on this host not obviously a wanted one. It only
makes the bot say what it is about to do.

Detection is from the URL alone, deliberately. Asking yt-dlp would be accurate
but costs a network round trip per pasted link before the user has even chosen a
format, and on YouTube that is the request that draws the bot check. A URL is
free and wrong only at the edges, where the cost is a line of text either shown
or not shown.

Note what is *not* flagged: ``watch?v=…&list=…``, the shape you get from copying
the address bar while a playlist plays. ``--no-playlist`` treats that as the one
video, which is what was asked for, so warning about it would put a notice on
most YouTube links anyone ever sends.
"""

from typing import Final
from urllib.parse import urlparse

_YOUTUBE_HOSTS: Final[frozenset[str]] = frozenset({
    'youtube.com',
    'm.youtube.com',
    'music.youtube.com',
    'youtu.be',
})
# Channel and feed pages. A handle (`/@someone`) is matched separately.
_YOUTUBE_COLLECTION_SEGMENTS: Final[frozenset[str]] = frozenset({
    'channel',
    'c',
    'user',
    'feed',
})

_SOUNDCLOUD_HOSTS: Final[frozenset[str]] = frozenset({
    'soundcloud.com',
    'm.soundcloud.com',
    'on.soundcloud.com',
})
# `/<user>/<tab>` pages, as opposed to `/<user>/<track>`.
_SOUNDCLOUD_TABS: Final[frozenset[str]] = frozenset({
    'albums',
    'likes',
    'popular-tracks',
    'reposts',
    'sets',
    'tracks',
})

_VIMEO_COLLECTION_SEGMENTS: Final[frozenset[str]] = frozenset({
    'album',
    'channels',
    'groups',
    'showcase',
})

_BANDCAMP_COLLECTION_SEGMENTS: Final[frozenset[str]] = frozenset({
    'album',
    'music',
})


def _segments(path: str) -> list[str]:
    return [segment for segment in path.split('/') if segment]


def _is_youtube_collection(segments: list[str]) -> bool:
    if not segments:
        return False
    first = segments[0]
    return (
        first == 'playlist'
        or first.startswith('@')
        or first in _YOUTUBE_COLLECTION_SEGMENTS
    )


def _is_soundcloud_collection(segments: list[str]) -> bool:
    if 'sets' in segments:
        # `/<user>/sets/<name>` is a playlist; `/<user>/sets` is all of them.
        return True
    if len(segments) == 1:
        # A bare artist page. `/discover` and `/search` land here too, and
        # neither is a single track either.
        return True
    return len(segments) == 2 and segments[1] in _SOUNDCLOUD_TABS  # noqa: PLR2004


def _is_vimeo_collection(segments: list[str]) -> bool:
    return bool(segments) and segments[0] in _VIMEO_COLLECTION_SEGMENTS


def _is_bandcamp_collection(segments: list[str]) -> bool:
    # Bandcamp gives every artist a subdomain, so the bare host is their page
    # and `/track/<name>` is the only single-item shape there is.
    return not segments or segments[0] in _BANDCAMP_COLLECTION_SEGMENTS


def is_collection_link(url: str) -> bool:
    """Whether this link points at many items, of which one will be downloaded.

    Unrecognised hosts are answered ``False``: silence is the behaviour this
    fork has always had, and a warning on an ordinary link is worse than no
    warning on an unusual one.
    """
    try:
        parsed = urlparse(url.strip())
        # `hostname` rather than `netloc`: it lower-cases, and drops the port
        # and any credentials, all of which would otherwise defeat the lookups.
        host = (parsed.hostname or '').removeprefix('www.')
    except ValueError:
        # A string that does not parse is not this function's problem — it will
        # fail later, with a message about the real cause.
        return False

    segments = _segments(parsed.path)

    if host in _YOUTUBE_HOSTS:
        return _is_youtube_collection(segments)
    if host in _SOUNDCLOUD_HOSTS:
        return _is_soundcloud_collection(segments)
    if host == 'vimeo.com':
        return _is_vimeo_collection(segments)
    if host == 'bandcamp.com' or host.endswith('.bandcamp.com'):
        return _is_bandcamp_collection(segments)
    return False
