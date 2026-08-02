"""Whatever importing the bot package needs before a test can run.

Only ``config_manager`` needs any of this: it reaches ``bot.core.config``, which
reads ``config.yml`` and the service environment at import time. Everything else
under test imports nothing beyond the standard library and ``yt_shared``.

The environment is read from the same files the containers use rather than
duplicated here, so a new required setting cannot make the tests drift from the
real defaults without someone noticing.
"""

import os
import shutil
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_CONFIG = _PACKAGE_ROOT / 'config.yml'
_CONFIG_EXAMPLE = _PACKAGE_ROOT / 'config-example.yml'


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        # setdefault: a value already in the environment wins, so a developer
        # can override one without editing anything.
        os.environ.setdefault(key.strip(), value.strip())


for _env_file in ('common.env', 'bot.env'):
    _load_env_file(_REPO_ROOT / 'envs' / _env_file)

# A real config.yml is left exactly as it is; only one created here is removed
# again afterwards.
_config_is_ours = not _CONFIG.exists()
if _config_is_ours:
    shutil.copyfile(_CONFIG_EXAMPLE, _CONFIG)


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    if _config_is_ours:
        _CONFIG.unlink(missing_ok=True)
