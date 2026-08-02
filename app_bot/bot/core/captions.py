"""The caption that travels with a delivered file.

Shared by the two paths that can deliver one — a fresh download and a file
Telegram already holds — so a repeat request produces the same caption as the
first one rather than something subtly different.
"""

from yt_shared.utils.common import format_bytes

from bot.core.schemas import VideoCaptionSchema


def build_video_caption_items(
    conf: VideoCaptionSchema,
    *,
    title: str | None,
    filename: str | None,
    url: str,
    file_size: int | None,
) -> list[str]:
    """Pick the caption lines the configuration asks for, skipping unknowns."""
    items: list[str] = []
    if conf.include_title and title:
        items.append(title)
    if conf.include_filename and filename:
        items.append(filename)
    if conf.include_link:
        items.append(url)
    if conf.include_size and file_size is not None:
        items.append(format_bytes(file_size))
    return items
