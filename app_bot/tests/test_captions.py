"""The caption both delivery paths build.

Shared so that a file served from the cache carries the same caption as the
first time it was downloaded, rather than something subtly different.
"""

import pytest

from bot.core.captions import build_video_caption_items
from bot.core.schemas import VideoCaptionSchema


def conf(**flags) -> VideoCaptionSchema:
    return VideoCaptionSchema(**{
        'include_title': False,
        'include_filename': False,
        'include_link': False,
        'include_size': False,
        **flags,
    })


def test_everything_on() -> None:
    items = build_video_caption_items(
        conf(
            include_title=True,
            include_filename=True,
            include_link=True,
            include_size=True,
        ),
        title='A title',
        filename='a.mp4',
        url='https://example.com/v',
        file_size=1024 * 1024,
    )
    assert items == ['A title', 'a.mp4', 'https://example.com/v', '1.0MiB']


def test_everything_off() -> None:
    items = build_video_caption_items(
        conf(),
        title='A title',
        filename='a.mp4',
        url='https://example.com/v',
        file_size=1024,
    )
    assert items == []


def test_order_is_fixed_regardless_of_which_are_on() -> None:
    items = build_video_caption_items(
        conf(include_size=True, include_title=True),
        title='A title',
        filename='a.mp4',
        url='https://example.com/v',
        file_size=1024,
    )
    assert items == ['A title', '1.0KiB']


@pytest.mark.parametrize('missing', ['title', 'filename'])
def test_an_unknown_value_is_skipped_rather_than_left_blank(missing: str) -> None:
    """A cached row may not carry every field; an empty line reads as a bug."""
    values = {'title': 'A title', 'filename': 'a.mp4'}
    values[missing] = None
    items = build_video_caption_items(
        conf(include_title=True, include_filename=True),
        url='https://example.com/v',
        file_size=None,
        **values,
    )
    assert '' not in items
    assert None not in items


def test_the_link_is_included_even_with_nothing_else_known() -> None:
    """It is the one thing always available, and what a retry needs."""
    items = build_video_caption_items(
        conf(include_title=True, include_link=True),
        title=None,
        filename=None,
        url='https://example.com/v',
        file_size=None,
    )
    assert items == ['https://example.com/v']


def test_a_missing_size_is_skipped() -> None:
    items = build_video_caption_items(
        conf(include_size=True),
        title=None,
        filename=None,
        url='https://example.com/v',
        file_size=None,
    )
    assert items == []
