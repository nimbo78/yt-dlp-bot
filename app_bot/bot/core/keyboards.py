"""Inline keyboard builders for format selection."""

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from yt_shared.enums import DownMediaType, VideoQuality

from bot.core.i18n import t
from bot.core.playlist_menu import (
    PLAYLIST_PREFIX,
    MenuEntry,
    build_menu,
)

# Callback data prefixes
MEDIA_TYPE_PREFIX = 'mt:'
QUALITY_PREFIX = 'q:'
DOWNLOAD_PREFIX = 'dl:'
CANCEL_PREFIX = 'cancel:'


def build_playlist_keyboard(
    entries: list[MenuEntry], url_id: str, page: int, language: str
) -> InlineKeyboardMarkup:
    """Render one page of a playlist as buttons.

    The layout is decided in `playlist_menu`, which knows nothing of Pyrogram
    and is therefore testable; this only turns the result into markup.
    """
    menu = build_menu(
        entries,
        url_id,
        cancel_label=t('format.button_cancel', language),
        cancel_data=f'{CANCEL_PREFIX}{url_id}',
        page=page,
    )
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(button.label, callback_data=button.data)
            for button in row
        ]
        for row in menu.rows
    ])


def build_media_type_keyboard(
    url_id: str, language: str, *, offer_playlist: bool = False
) -> InlineKeyboardMarkup:
    """Build keyboard for selecting media type (Video/Audio).

    A link that points at many items gets one extra button, offering to list
    them. Only then: enumerating costs a request to the site, so it happens
    because somebody asked, not because a link looked like a playlist.
    """
    playlist_row = (
        [
            [
                InlineKeyboardButton(
                    t('format.button_show_playlist', language),
                    callback_data=f'{PLAYLIST_PREFIX}{url_id}',
                ),
            ]
        ]
        if offer_playlist
        else []
    )
    return InlineKeyboardMarkup([
        *playlist_row,
        [
            InlineKeyboardButton(
                t('format.button_video', language),
                callback_data=f'{MEDIA_TYPE_PREFIX}{DownMediaType.VIDEO}:{url_id}',
            ),
            InlineKeyboardButton(
                t('format.button_audio', language),
                callback_data=f'{MEDIA_TYPE_PREFIX}{DownMediaType.AUDIO}:{url_id}',
            ),
        ],
        [
            InlineKeyboardButton(
                t('format.button_both', language),
                callback_data=f'{MEDIA_TYPE_PREFIX}{DownMediaType.AUDIO_VIDEO}:{url_id}',
            ),
        ],
        [
            InlineKeyboardButton(
                t('format.button_cancel', language),
                callback_data=f'{CANCEL_PREFIX}{url_id}',
            ),
        ],
    ])


def build_quality_keyboard(
    url_id: str, media_type: DownMediaType, language: str
) -> InlineKeyboardMarkup:
    """Build keyboard for selecting video quality."""
    if media_type == DownMediaType.AUDIO:
        # For audio, skip quality selection and go directly to download
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    t('format.button_download_audio', language),
                    callback_data=f'{DOWNLOAD_PREFIX}{media_type}:{VideoQuality.BEST}:{url_id}',
                ),
            ],
            [
                InlineKeyboardButton(
                    t('format.button_back', language),
                    callback_data=f'{MEDIA_TYPE_PREFIX}back:{url_id}',
                ),
            ],
        ])

    # For video, show quality options
    quality_buttons = [
        [
            InlineKeyboardButton(
                t('format.button_best', language),
                callback_data=f'{DOWNLOAD_PREFIX}{media_type}:{VideoQuality.BEST}:{url_id}',
            ),
        ],
        [
            InlineKeyboardButton(
                '4K',
                callback_data=f'{DOWNLOAD_PREFIX}{media_type}:{VideoQuality.UHD_4K}:{url_id}',
            ),
            InlineKeyboardButton(
                '1440p',
                callback_data=f'{DOWNLOAD_PREFIX}{media_type}:{VideoQuality.QHD_1440P}:{url_id}',
            ),
        ],
        [
            InlineKeyboardButton(
                '1080p',
                callback_data=f'{DOWNLOAD_PREFIX}{media_type}:{VideoQuality.FHD_1080P}:{url_id}',
            ),
            InlineKeyboardButton(
                '720p',
                callback_data=f'{DOWNLOAD_PREFIX}{media_type}:{VideoQuality.HD_720P}:{url_id}',
            ),
        ],
        [
            InlineKeyboardButton(
                '480p',
                callback_data=f'{DOWNLOAD_PREFIX}{media_type}:{VideoQuality.SD_480P}:{url_id}',
            ),
            InlineKeyboardButton(
                '360p',
                callback_data=f'{DOWNLOAD_PREFIX}{media_type}:{VideoQuality.LD_360P}:{url_id}',
            ),
        ],
        [
            InlineKeyboardButton(
                t('format.button_back', language),
                callback_data=f'{MEDIA_TYPE_PREFIX}back:{url_id}',
            ),
            InlineKeyboardButton(
                t('format.button_cancel', language),
                callback_data=f'{CANCEL_PREFIX}{url_id}',
            ),
        ],
    ]

    return InlineKeyboardMarkup(quality_buttons)
