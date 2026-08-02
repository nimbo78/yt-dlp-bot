"""Type resolution and coercion behind ``/config set``.

The command receives everything as a string, so the config manager has to work
out what the schema expects before writing it back. Both halves of that have
gone wrong before: a path the file had never mentioned was rejected as unknown,
and a value with no previous value to copy the type from was written as a
string.
"""

from pathlib import Path

import pytest
from ruamel.yaml import YAML
from ruamel.yaml.scalarbool import ScalarBoolean
from ruamel.yaml.scalarint import ScalarInt
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from bot.core.config.config_manager import ConfigManager


@pytest.fixture
def manager() -> ConfigManager:
    return ConfigManager()


class TestResolveDeclaredType:
    """The schema is the source of truth, not whatever the file happens to hold."""

    @pytest.mark.parametrize(
        ('path', 'expected'),
        [
            ('telegram.lang_code', str),
            ('telegram.api_hash', str),
            ('telegram.max_upload_tasks', int),
            ('telegram.delete_source_message', bool),
            ('ytdlp.version_check_enabled', bool),
            ('ytdlp.version_check_interval', int),
        ],
    )
    def test_known_paths(self, manager: ConfigManager, path: str, expected: type) -> None:
        assert manager._resolve_declared_type(path.split('.')) is expected

    def test_optional_is_unwrapped_to_the_real_type(self, manager: ConfigManager) -> None:
        """``bool | None`` has to resolve to ``bool``, not to the union."""
        assert (
            manager._resolve_declared_type(
                ['telegram', 'api', 'upload_video_max_file_size']
            )
            is int
        )

    @pytest.mark.parametrize(
        'path',
        [
            'telegram.nonexistent',
            'nonexistent.at.all',
            # Paths through a list cannot be resolved: allowed_users is a list of
            # models, and there is no single element the path refers to.
            'telegram.allowed_users.lang_code',
        ],
    )
    def test_unresolvable_paths(self, manager: ConfigManager, path: str) -> None:
        assert manager._resolve_declared_type(path.split('.')) is None


class TestConvertValue:
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            ('true', True),
            ('True', True),
            ('1', True),
            ('yes', True),
            ('on', True),
            ('false', False),
            ('False', False),
            ('0', False),
            ('no', False),
            ('anything else', False),
        ],
    )
    def test_bool(self, manager: ConfigManager, text: str, expected: bool) -> None:
        assert manager._convert_value(text, None, bool) is expected

    def test_int(self, manager: ConfigManager) -> None:
        assert manager._convert_value('10', None, int) == 10

    def test_float(self, manager: ConfigManager) -> None:
        assert manager._convert_value('1.5', None, float) == 1.5

    def test_str_is_passed_through(self, manager: ConfigManager) -> None:
        assert manager._convert_value('uk', None, str) == 'uk'

    def test_an_unconvertible_int_raises(self, manager: ConfigManager) -> None:
        """Better to refuse than to write nonsense into the config."""
        with pytest.raises(ValueError):
            manager._convert_value('not a number', None, int)

    def test_falls_back_to_the_previous_value_type(self, manager: ConfigManager) -> None:
        """With no declared type, the value already in the file decides."""
        assert manager._convert_value('7', 3, None) == 7
        assert manager._convert_value('true', False, None) is True

    def test_unknown_type_is_left_as_text(self, manager: ConfigManager) -> None:
        assert manager._convert_value('x', None, list) == 'x'


class TestToPlainPython:
    """ruamel keeps its own scalar types; pydantic will not accept them."""

    def test_scalars(self, manager: ConfigManager) -> None:
        assert manager._to_plain_python(ScalarInt(5)) == 5
        assert type(manager._to_plain_python(ScalarInt(5))) is int
        assert manager._to_plain_python(ScalarBoolean(1)) is True
        assert type(manager._to_plain_python(DoubleQuotedScalarString('x'))) is str

    def test_nested_structures(self, manager: ConfigManager) -> None:
        yaml = YAML()
        loaded = yaml.load('a:\n  b: !!bool True\n  c:\n    - 1\n    - 2\n')
        plain = manager._to_plain_python(loaded)
        assert plain == {'a': {'b': True, 'c': [1, 2]}}
        assert type(plain) is dict
        assert type(plain['a']['c']) is list


class TestValidateConfig:
    """Validation runs before anything is written, so a bad value never lands."""

    @pytest.fixture
    def raw(self, manager: ConfigManager) -> dict:
        example = Path(manager._config_dir) / 'config-example.yml'
        return YAML().load(example.read_text(encoding='utf-8'))

    def test_the_shipped_example_is_valid(self, manager: ConfigManager, raw: dict) -> None:
        assert manager._validate_config(raw) is not None

    def test_a_supported_language_is_accepted(
        self, manager: ConfigManager, raw: dict
    ) -> None:
        raw['telegram']['lang_code'] = 'uk'
        assert manager._validate_config(raw).telegram.lang_code == 'uk'

    def test_language_case_is_normalised(self, manager: ConfigManager, raw: dict) -> None:
        raw['telegram']['lang_code'] = 'LV'
        assert manager._validate_config(raw).telegram.lang_code == 'lv'

    def test_an_unsupported_language_is_refused(
        self, manager: ConfigManager, raw: dict
    ) -> None:
        raw['telegram']['lang_code'] = 'de-AT'
        with pytest.raises(ValueError, match='unsupported language'):
            manager._validate_config(raw)

    def test_a_per_user_language_is_validated_too(
        self, manager: ConfigManager, raw: dict
    ) -> None:
        raw['telegram']['allowed_users'][0]['lang_code'] = 'zz'
        with pytest.raises(ValueError, match='unsupported language'):
            manager._validate_config(raw)
