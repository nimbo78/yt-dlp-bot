"""Whatever importing the API package needs before a test can run.

``api.config`` reads the service environment at import time. It is taken from
the files the containers already use rather than duplicated here, so a newly
required setting cannot make the tests drift from the real defaults unnoticed.
"""

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        os.environ.setdefault(key.strip(), value.strip())


for _env_file in ('common.env', 'api.env'):
    _load_env_file(_REPO_ROOT / 'envs' / _env_file)
