"""Who is allowed to reach the API.

The route below stands in for the versioned routers: what matters is the
dependency, and building a one-route app keeps the test away from Redis,
RabbitMQ and the database, none of which have anything to do with the answer.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.common.security import require_token, warn_if_unauthenticated
from api.config import settings

TOKEN = 'a-real-token-value'  # noqa: S105


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()

    @app.get('/protected', dependencies=[Depends(require_token)])
    async def protected() -> dict:
        return {'ok': True}

    @app.get('/open')
    async def open_route() -> dict:
        return {'ok': True}

    return TestClient(app)


@pytest.fixture
def with_token(monkeypatch) -> str:
    monkeypatch.setattr(settings, 'API_TOKEN', TOKEN)
    return TOKEN


@pytest.fixture
def without_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'API_TOKEN', '')


class TestTokenConfigured:
    def test_the_right_token_is_accepted(
        self, client: TestClient, with_token: str
    ) -> None:
        response = client.get(
            '/protected', headers={'Authorization': f'Bearer {with_token}'}
        )
        assert response.status_code == 200

    def test_no_header_is_rejected(self, client: TestClient, with_token: str) -> None:
        response = client.get('/protected')
        assert response.status_code == 401
        assert response.headers['WWW-Authenticate'] == 'Bearer'

    def test_a_wrong_token_is_rejected(
        self, client: TestClient, with_token: str
    ) -> None:
        response = client.get(
            '/protected', headers={'Authorization': 'Bearer not-the-token'}
        )
        assert response.status_code == 401

    def test_a_prefix_of_the_token_is_rejected(
        self, client: TestClient, with_token: str
    ) -> None:
        """The comparison is whole-value, not a prefix match."""
        response = client.get(
            '/protected', headers={'Authorization': f'Bearer {with_token[:-1]}'}
        )
        assert response.status_code == 401

    def test_an_empty_token_is_rejected(
        self, client: TestClient, with_token: str
    ) -> None:
        response = client.get('/protected', headers={'Authorization': 'Bearer '})
        assert response.status_code == 401

    @pytest.mark.parametrize(
        'header',
        [
            'Basic dXNlcjpwYXNz',
            'Token a-real-token-value',
            'a-real-token-value',
            'Bearer',
        ],
    )
    def test_a_wrong_scheme_is_rejected(
        self, client: TestClient, with_token: str, header: str
    ) -> None:
        """The token alone, or under another scheme, must not be enough."""
        response = client.get('/protected', headers={'Authorization': header})
        assert response.status_code == 401

    def test_the_scheme_is_matched_case_insensitively(
        self, client: TestClient, with_token: str
    ) -> None:
        """HTTP schemes are case-insensitive, and clients differ."""
        response = client.get(
            '/protected', headers={'Authorization': f'bearer {with_token}'}
        )
        assert response.status_code == 200

    def test_an_unprotected_route_is_still_open(
        self, client: TestClient, with_token: str
    ) -> None:
        """The health check must keep working without a credential."""
        assert client.get('/open').status_code == 200


class TestTokenNotConfigured:
    """Left unset on purpose: the port binding is what protects the API then."""

    def test_a_request_without_a_header_is_allowed(
        self, client: TestClient, without_token: None
    ) -> None:
        assert client.get('/protected').status_code == 200

    def test_a_stray_header_is_ignored(
        self, client: TestClient, without_token: None
    ) -> None:
        response = client.get(
            '/protected', headers={'Authorization': 'Bearer anything at all'}
        )
        assert response.status_code == 200


class TestStartupWarning:
    def test_warns_when_no_token_is_set(self, without_token: None, caplog) -> None:
        warn_if_unauthenticated()
        assert 'API_TOKEN is not set' in caplog.text

    def test_stays_quiet_when_a_token_is_set(self, with_token: str, caplog) -> None:
        warn_if_unauthenticated()
        assert caplog.text == ''
