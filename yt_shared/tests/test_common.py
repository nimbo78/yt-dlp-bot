"""Helpers shared by the services.

``format_bytes`` renders every size the user ever sees — in the progress line,
in the file card, in the upload counter — so its edges are worth pinning down.
"""

import pytest
from yt_shared.utils.common import calculate_aspect_ratio, format_bytes


@pytest.mark.parametrize(
    ('num', 'expected'),
    [
        (0, '0.0B'),
        (1, '1.0B'),
        (1023, '1023.0B'),
        (1024, '1.0KiB'),
        (1536, '1.5KiB'),
        (1024**2, '1.0MiB'),
        (52_428_800, '50.0MiB'),
        (1024**3, '1.0GiB'),
        (1024**4, '1.0TiB'),
    ],
)
def test_format_bytes(num: int, expected: str) -> None:
    assert format_bytes(num) == expected


def test_format_bytes_takes_a_suffix() -> None:
    assert format_bytes(1024, suffix='') == '1.0Ki'


def test_format_bytes_handles_a_negative() -> None:
    """Not expected, but it must not loop or raise."""
    assert format_bytes(-1024) == '-1.0KiB'


@pytest.mark.parametrize(
    ('width', 'height', 'expected'),
    [
        (1920, 1080, (16, 9)),
        (1280, 720, (16, 9)),
        (854, 480, (427, 240)),  # not exactly 16:9, which is why callers need slack
        (1080, 1920, (9, 16)),
        (100, 100, (1, 1)),
    ],
)
def test_calculate_aspect_ratio(width: int, height: int, expected: tuple) -> None:
    assert calculate_aspect_ratio(width, height) == expected
