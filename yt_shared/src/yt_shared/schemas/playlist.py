"""Asking what is inside a playlist, and hearing back.

The bot cannot answer this itself: yt-dlp lives in `app_worker` alone, and
putting it in `app_bot` means relocking that package. So the question goes over
RabbitMQ like everything else that crosses the two.

A failure comes back as a result carrying `error`, not as a message that is
never answered. Something is waiting on the other end with a keyboard on
screen, and "no reply, ever" is the one outcome it cannot render.
"""

from typing import Literal

from pydantic import Field

from yt_shared.enums import RabbitPayloadType
from yt_shared.schemas.base import StrictBaseRabbitPayloadModel, StrictRealBaseModel

# What the bot can offer and a small host can enumerate. A channel with ten
# thousand videos is not a menu, and the worker cuts at this too.
MAX_PLAYLIST_ENTRIES = 100


class PlaylistRequestPayload(StrictBaseRabbitPayloadModel):
    """Tell me what is in this, without downloading any of it."""

    type: Literal[RabbitPayloadType.PLAYLIST_REQUEST] = (
        RabbitPayloadType.PLAYLIST_REQUEST
    )
    # Names the pending download this belongs to, so the answer can find the
    # keyboard that asked. See `bot.core.pending_downloads.generate_url_id`.
    url_id: str
    url: str
    from_chat_id: int
    ack_message_id: int
    limit: int = Field(default=MAX_PLAYLIST_ENTRIES, gt=0, le=MAX_PLAYLIST_ENTRIES)


class PlaylistEntryPayload(StrictRealBaseModel):
    """One item, as offered on a button."""

    # Position in the source, which is not the position in this list: entries
    # that cannot be opened are dropped and the numbering does not close up.
    index: int
    title: str
    url: str


class PlaylistResultPayload(StrictBaseRabbitPayloadModel):
    """What is in it — or why that could not be answered."""

    type: Literal[RabbitPayloadType.PLAYLIST_RESULT] = (
        RabbitPayloadType.PLAYLIST_RESULT
    )
    url_id: str
    from_chat_id: int
    ack_message_id: int
    title: str = 'Playlist'
    # Pydantic copies field defaults per instance, so this is not shared state.
    entries: list[PlaylistEntryPayload] = []  # noqa: RUF012
    # What the source claimed before the limit and the dropping, so "10 of 250"
    # does not quietly render as "10".
    total: int = 0
    # yt-dlp's own words, classified by the bot like any other failure. Unset on
    # success; set means `entries` says nothing.
    error: str | None = None
