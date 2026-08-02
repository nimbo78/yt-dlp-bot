from yt_shared.enums import MediaFileType
from yt_shared.schemas.base import RealBaseModel


class CachedFile(RealBaseModel):
    """A file Telegram already holds, ready to be sent again by id.

    Enough to re-send it without touching the disk. Telegram keeps the cover it
    was uploaded with, so no thumbnail is carried here.
    """

    file_id: str
    file_type: MediaFileType
    title: str | None = None
    filename: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    file_size: int | None = None
