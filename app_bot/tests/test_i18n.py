"""Catalogue integrity across every supported language.

These are the checks that were being run by hand while the catalogues were
written. A missing key or a renamed placeholder does not raise at import time —
it surfaces as a broken message in front of whoever happened to trigger it — so
the whole point is to catch it here instead.
"""

import json
import re
from pathlib import Path

import pytest

from bot.core import i18n

LOCALES_DIR = Path(i18n.__file__).resolve().parent.parent / 'locales'
PLACEHOLDER = re.compile(r'{(\w+)}')


def placeholders(template: str) -> set[str]:
    return set(PLACEHOLDER.findall(template))


TRANSLATIONS = [lang for lang in i18n.LANGUAGES if lang != i18n.FALLBACK_LANGUAGE]


def test_fallback_language_is_supported() -> None:
    assert i18n.FALLBACK_LANGUAGE in i18n.LANGUAGES


def test_every_language_has_a_file() -> None:
    on_disk = {path.stem for path in LOCALES_DIR.glob('*.json')}
    assert on_disk == set(i18n.LANGUAGES)


def test_no_language_is_listed_twice() -> None:
    assert len(set(i18n.LANGUAGES)) == len(i18n.LANGUAGES)


def test_master_catalogue_is_not_empty() -> None:
    assert i18n._CATALOGUES[i18n.FALLBACK_LANGUAGE]


def test_no_translation_is_missing_a_key() -> None:
    assert i18n.missing_keys() == {}


def test_no_translation_invents_a_key() -> None:
    assert i18n.unknown_keys() == {}


@pytest.mark.parametrize('language', TRANSLATIONS)
def test_placeholders_match_english(language: str) -> None:
    """A renamed or dropped placeholder breaks formatting at render time."""
    master = i18n._CATALOGUES[i18n.FALLBACK_LANGUAGE]
    for key, template in sorted(i18n._CATALOGUES[language].items()):
        assert placeholders(template) == placeholders(master[key]), (
            f'{language}: {key}'
        )


@pytest.mark.parametrize('language', i18n.LANGUAGES)
def test_no_stray_angle_brackets(language: str) -> None:
    """Telegram parses the message as HTML and rejects a malformed one."""
    allowed_tag = re.compile(r'</?(?:b|code)>|&lt;|&gt;|&amp;')
    for key, template in sorted(i18n._CATALOGUES[language].items()):
        stripped = allowed_tag.sub('', template)
        assert '<' not in stripped and '>' not in stripped, f'{language}: {key}'


@pytest.mark.parametrize('language', i18n.LANGUAGES)
def test_html_tags_are_balanced(language: str) -> None:
    for key, template in sorted(i18n._CATALOGUES[language].items()):
        for tag in ('b', 'code'):
            assert template.count(f'<{tag}>') == template.count(f'</{tag}>'), (
                f'{language}: {key}: <{tag}>'
            )


@pytest.mark.parametrize('language', i18n.LANGUAGES)
def test_catalogue_file_is_valid_json_and_flattens_cleanly(language: str) -> None:
    """Every leaf must be a string; a stray list or number would fail at render."""
    raw = json.loads((LOCALES_DIR / f'{language}.json').read_text(encoding='utf-8'))
    for key, value in i18n._flatten(raw).items():
        assert isinstance(value, str), f'{language}: {key} is {type(value).__name__}'


class TestLookup:
    def test_returns_the_translation(self) -> None:
        assert i18n.t('format.button_cancel', 'ru') == '❌ Отмена'

    def test_fills_placeholders(self) -> None:
        rendered = i18n.t('progress.downloading', 'en', percent='42.5')
        assert '42.5%' in rendered

    def test_falls_back_to_english_for_an_untranslated_key(self, monkeypatch) -> None:
        monkeypatch.setitem(i18n._CATALOGUES, 'ru', {})
        assert i18n.t('format.button_cancel', 'ru') == i18n.t(
            'format.button_cancel', 'en'
        )

    def test_falls_back_to_english_for_an_unknown_language(self) -> None:
        assert i18n.t('format.button_cancel', 'xx') == i18n.t(
            'format.button_cancel', 'en'
        )

    def test_no_language_means_english(self) -> None:
        assert i18n.t('format.button_cancel') == i18n.t('format.button_cancel', 'en')

    def test_an_unknown_key_returns_itself_rather_than_raising(self) -> None:
        """Ugly, but a missing string must never take a download down."""
        assert i18n.t('no.such.key', 'en') == 'no.such.key'

    def test_a_wrong_placeholder_returns_the_unfilled_template(self) -> None:
        assert i18n.t('progress.downloading', 'en', wrong='x') == (
            i18n._CATALOGUES['en']['progress.downloading']
        )


class TestHasMessage:
    """Guards keys that arrive from the worker, which deploys separately."""

    def test_known_key(self) -> None:
        assert i18n.has_message('postprocess.merger')

    def test_unknown_key(self) -> None:
        assert not i18n.has_message('postprocess.invented_by_a_newer_worker')

    def test_none(self) -> None:
        assert not i18n.has_message(None)

    def test_empty(self) -> None:
        assert not i18n.has_message('')


def test_worker_step_keys_all_exist() -> None:
    """The worker names messages the bot has to be able to render.

    The two services are deployed separately, so this pairing is only checked
    by reading both files — unless something checks it here.
    """
    repo_root = Path(i18n.__file__).resolve().parents[3]
    worker_progress = repo_root / 'app_worker' / 'worker' / 'core' / 'progress.py'
    assert worker_progress.is_file(), f'worker not where expected: {worker_progress}'
    source = worker_progress.read_text(encoding='utf-8')
    keys = re.findall(r"'((?:postprocess|notice)\.\w+)'", source)
    assert keys, 'no message keys found in the worker; did the file move?'
    for key in keys:
        assert i18n.has_message(key), f'worker names a key the bot lacks: {key}'
