import re

from pydantic import DirectoryPath, PositiveInt, field_validator
from yt_shared.config import CommonSettings

_RATE_RE = re.compile(r'\d+(\.\d+)?[KMG]?', re.IGNORECASE)
_LANG_RE = re.compile(r'[a-z]{2,3}(-[A-Za-z0-9]{2,4})?')


class WorkerSettings(CommonSettings):
    APPLICATION_NAME: str
    # How many downloads actually run at once. 1 is sequential, which is what
    # a small host wants. Positive rather than plain int: zero would stop the
    # worker dead with no error anywhere.
    MAX_SIMULTANEOUS_DOWNLOADS: PositiveInt
    STORAGE_PATH: DirectoryPath
    THUMBNAIL_FRAME_SECOND: float
    INSTAGRAM_ENCODE_TO_H264: bool
    FACEBOOK_ENCODE_TO_H264: bool
    MAX_DOWNLOAD_THREADS: str
    # Refuse to start a download when less than this is free in the staging
    # area, and keep it in reserve when sizing a download. 0 disables both.
    MIN_FREE_SPACE_MB: int = 512
    DOWNLOAD_RATE_LIMIT: str = ''
    METADATA_LANGUAGE: str = ''

    @field_validator('MAX_DOWNLOAD_THREADS')
    @classmethod
    def validate_max_download_threads(cls, value: str) -> str:
        """Value must be integer enclosed as string."""
        if not value.isdigit():
            raise ValueError('Value must be integer enclosed as string.')
        return value

    @field_validator('METADATA_LANGUAGE')
    @classmethod
    def validate_metadata_language(cls, value: str) -> str:
        """Check the language tag, e.g. `ru` or `pt-BR`; empty keeps the default.

        Only the shape is checked here. Which tags a site actually offers is the
        site's business, and yt-dlp names the supported ones when it refuses.
        """
        value = value.strip()
        if value and not _LANG_RE.fullmatch(value):
            raise ValueError(
                'Value must be a language tag such as "ru" or "pt-BR", '
                'or empty to leave the site default.'
            )
        return value

    @field_validator('DOWNLOAD_RATE_LIMIT')
    @classmethod
    def validate_download_rate_limit(cls, value: str) -> str:
        """Bytes per second, optionally suffixed; empty means no limit.

        Checked here so a typo stops the worker at startup instead of failing
        every single download.
        """
        value = value.strip()
        if value and not _RATE_RE.fullmatch(value):
            raise ValueError(
                'Value must be a download rate such as "500K" or "4.2M", '
                'or empty for no limit.'
            )
        return value


settings = WorkerSettings()
