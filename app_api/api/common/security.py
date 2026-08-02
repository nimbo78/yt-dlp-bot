"""Authentication for the HTTP API.

The API queues downloads into whichever chats the bot is configured for, so an
open port is not merely a read-only leak: anyone who reaches it can make the bot
send files to those chats. It is therefore closed by default in two different
ways, and either one alone is enough.

* ``API_TOKEN`` unset — the service still runs, and ``docker-compose.yml``
  publishes the port on ``127.0.0.1`` only, so nothing off the host can reach
  it. This keeps an existing deployment working after an upgrade.
* ``API_TOKEN`` set — every versioned route requires
  ``Authorization: Bearer <token>``. Exposing the port beyond the host is then
  a deliberate choice, made in ``docker-compose.override.yml``.

The health check stays open either way, so container health checks and uptime
monitors keep working without holding a credential.
"""

import logging
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.config import settings

logger = logging.getLogger(__name__)

# auto_error=False so a missing header reaches us as None: the answer depends on
# whether a token is configured at all, which HTTPBearer cannot know.
_bearer = HTTPBearer(auto_error=False, description='Value of API_TOKEN')


def warn_if_unauthenticated() -> None:
    """Say so at startup, once, when nothing is guarding the API."""
    if not settings.API_TOKEN:
        logger.warning(
            'API_TOKEN is not set: the API accepts every request. This is safe '
            'only while the port stays bound to 127.0.0.1. Set API_TOKEN in '
            'envs/api.local.env before publishing it anywhere else.'
        )


def require_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    """Reject a request that does not carry the configured token."""
    expected = settings.API_TOKEN
    if not expected:
        # Deliberately unauthenticated; the port binding is the protection.
        return

    if credentials is None or not secrets.compare_digest(
        credentials.credentials, expected
    ):
        # compare_digest keeps the comparison independent of how much of the
        # token matched, so a wrong one leaks nothing through timing.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or missing API token',
            headers={'WWW-Authenticate': 'Bearer'},
        )
