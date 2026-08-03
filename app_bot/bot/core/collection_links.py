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

There are two separate questions here and they have different answers, which is
why there are two functions.

*Is anything being lost?* — :func:`is_collection_link`. This drives the warning.
``watch?v=…&list=…`` answers **no**: that is the shape you get from copying the
address bar while a playlist plays, ``--no-playlist`` treats it as the one video
you were watching, and nothing is dropped. Warning about it would put a notice
on most YouTube links anyone ever sends.

*Is there a list worth offering?* — :func:`carries_playlist`. This drives the
button. The same ``watch?v=…&list=…`` answers **yes**: the playlist is right
there in the link, and somebody who pasted it may well want to pick from it
rather than take the one video. Offering costs a button nobody has to press.
"""

from typing import Final
from urllib.parse import parse_qs, urlparse

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


def _parse(url: str) -> tuple[str, list[str], str] | None:
    """Split a URL into host without `www.`, path segments, and raw query.

    ``None`` when the string does not parse — that is not this module's problem
    to report, and it will fail later with a message about the real cause.
    """
    try:
        parsed = urlparse(url.strip())
        # `hostname` rather than `netloc`: it lower-cases, and drops the port
        # and any credentials, all of which would otherwise defeat the lookups.
        host = (parsed.hostname or '').removeprefix('www.')
    except ValueError:
        return None
    return host, _segments(parsed.path), parsed.query


def carries_playlist(url: str) -> bool:
    """Whether there is a list here worth offering to pick from.

    Broader than :func:`is_collection_link` by exactly one case: a YouTube video
    opened from within a playlist, `watch?v=…&list=…`. Nothing is being lost
    there, so it earns no warning — but the playlist is named in the link, and
    somebody who pasted it may want the list rather than the one video.

    Auto-generated mixes (`list=RD…`) are included too. They are not playlists
    anybody made, but the rule that excludes them is one more thing to be wrong
    about, and an unwanted button is a far smaller cost than a missing one.
    """
    if is_collection_link(url):
        return True
    parsed = _parse(url)
    if parsed is None:
        return False
    host, _, query = parsed
    if host not in _YOUTUBE_HOSTS:
        # Only YouTube names a playlist in the query of a video link. Elsewhere
        # a list is its own address, which the check above already covers.
        return False
    return bool(parse_qs(query).get('list'))


def is_collection_link(url: str) -> bool:
    """Whether this link points at many items, of which one will be downloaded.

    Unrecognised hosts are answered ``False``: silence is the behaviour this
    fork has always had, and a warning on an ordinary link is worse than no
    warning on an unusual one.
    """
    parsed = _parse(url)
    if parsed is None:
        return False
    host, segments, _ = parsed

    if host in _YOUTUBE_HOSTS:
        return _is_youtube_collection(segments)
    if host in _SOUNDCLOUD_HOSTS:
        return _is_soundcloud_collection(segments)
    if host == 'vimeo.com':
        return _is_vimeo_collection(segments)
    if host == 'bandcamp.com' or host.endswith('.bandcamp.com'):
        return _is_bandcamp_collection(segments)
    return False
