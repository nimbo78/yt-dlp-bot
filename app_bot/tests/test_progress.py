"""Rendering of the single status message that tracks a task.

Every field of the payload is optional, because the worker only knows some of
them some of the time, so the interesting cases are the sparse ones.
"""

import pytest
from yt_shared.enums import ProgressStage
from yt_shared.schemas.progress import ProgressPayload

from bot.core.progress import (
    _format_eta,
    _progress_bar,
    format_download_progress,
    format_upload_progress,
)


def payload(**kwargs) -> ProgressPayload:
    return ProgressPayload(
        from_chat_id=1,
        ack_message_id=2,
        stage=kwargs.pop('stage', ProgressStage.DOWNLOADING),
        **kwargs,
    )


@pytest.mark.parametrize(
    ('seconds', 'expected'),
    [(0, '0:00'), (9, '0:09'), (95, '1:35'), (3600, '1:00:00'), (3725, '1:02:05')],
)
def test_format_eta(seconds: int, expected: str) -> None:
    assert _format_eta(seconds) == expected


@pytest.mark.parametrize(
    ('percent', 'filled'),
    [(0, 0), (5, 0), (10, 1), (42.5, 4), (99.9, 9), (100, 10)],
)
def test_progress_bar(percent: float, filled: int) -> None:
    bar = _progress_bar(percent)
    assert len(bar) == 10
    assert bar.count('▰') == filled


@pytest.mark.parametrize('percent', [-10, 150])
def test_progress_bar_survives_impossible_percentages(percent: float) -> None:
    assert len(_progress_bar(percent)) == 10


class TestDownloading:
    def test_all_fields(self) -> None:
        text = format_download_progress(
            payload(
                percent=42.5,
                downloaded_bytes=52_428_800,
                total_bytes=123_456_789,
                speed=1_572_864.0,
                eta=95,
            ),
            'en',
        )
        assert 'Downloading' in text
        assert '42.5%' in text
        assert '1:35 left' in text
        assert '50.0MiB of 117.7MiB' in text
        assert '1.5MiB/s' in text

    def test_nothing_known_yet(self) -> None:
        """Before the first bytes arrive there is no percentage and no bar."""
        text = format_download_progress(payload(), 'en')
        assert '<b>Downloading</b>' in text
        assert '%' not in text
        assert '▰' not in text and '▱' not in text

    def test_size_without_a_known_total(self) -> None:
        text = format_download_progress(payload(downloaded_bytes=1_048_576), 'en')
        assert '1.0MiB' in text
        assert ' of ' not in text

    def test_a_notice_is_rendered(self) -> None:
        text = format_download_progress(
            payload(detail_key='notice.cookies_rejected'), 'en'
        )
        assert 'Cookies were rejected' in text

    def test_an_unknown_notice_key_is_dropped(self) -> None:
        """A newer worker must not put a raw key in front of anyone."""
        text = format_download_progress(payload(detail_key='notice.from_the_future'), 'en')
        assert 'notice.' not in text


class TestPostProcessing:
    def test_named_step(self) -> None:
        text = format_download_progress(
            payload(
                stage=ProgressStage.POSTPROCESSING,
                detail_key='postprocess.merger',
                elapsed=3725,
            ),
            'en',
        )
        assert 'Processing' in text
        assert 'Merging video and audio' in text
        assert '1:02:05 elapsed' in text

    def test_unnamed_step_falls_back_to_the_generic_line(self) -> None:
        text = format_download_progress(
            payload(stage=ProgressStage.POSTPROCESSING), 'en'
        )
        assert 'Merging and converting' in text

    def test_unknown_step_key_falls_back_too(self) -> None:
        text = format_download_progress(
            payload(
                stage=ProgressStage.POSTPROCESSING,
                detail_key='postprocess.invented_by_a_newer_worker',
            ),
            'en',
        )
        assert 'postprocess.' not in text
        assert 'Merging and converting' in text

    def test_no_percentage_is_shown(self) -> None:
        """Post-processing reports none, so a bar would be a lie."""
        text = format_download_progress(
            payload(stage=ProgressStage.POSTPROCESSING, elapsed=10), 'en'
        )
        assert '%' not in text
        assert '▰' not in text


class TestUploading:
    def test_with_a_known_total(self) -> None:
        text = format_upload_progress(700_000_000, 1_400_000_000, 'en')
        assert 'Uploading' in text
        assert '50.0%' in text
        assert 'of' in text

    def test_without_a_total(self) -> None:
        text = format_upload_progress(1_000, 0, 'en')
        assert 'Uploading' in text
        assert '%' not in text

    def test_never_exceeds_one_hundred_percent(self) -> None:
        """Pyrogram can report the final chunk as slightly past the total."""
        text = format_upload_progress(1_100, 1_000, 'en')
        assert '100.0%' in text


@pytest.mark.parametrize('language', ['en', 'ru', 'he', 'lv', 'uk', 'de', 'el'])
def test_every_language_renders_without_raising(language: str) -> None:
    full = payload(
        percent=42.5,
        downloaded_bytes=52_428_800,
        total_bytes=123_456_789,
        speed=1_572_864.0,
        eta=95,
    )
    assert format_download_progress(full, language)
    assert format_upload_progress(700, 1_400, language)
    assert format_download_progress(
        payload(stage=ProgressStage.POSTPROCESSING, detail_key='postprocess.merger'),
        language,
    )
