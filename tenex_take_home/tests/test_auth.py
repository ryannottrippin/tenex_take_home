"""
Tests for all /auth/* routes.

/auth/me reads request.session directly (no Depends), so it needs the
session_client fixture (real signed cookie).  The other routes either need no
auth or are tested with the unauthenticated client fixture.

External HTTP calls (Google token exchange, userinfo) are mocked with
unittest.mock so tests never hit the network.
"""

from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

class TestAuthMe:
    def test_unauthenticated_returns_401(self, client):
        response = client.get("/auth/me")
        assert response.status_code == 401

    def test_unauthenticated_body_has_null_user(self, client):
        response = client.get("/auth/me")
        assert response.json() == {"user": None}

    def test_authenticated_returns_200(self, session_client):
        response = session_client.get("/auth/me")
        assert response.status_code == 200

    def test_authenticated_returns_correct_email(self, session_client):
        response = session_client.get("/auth/me")
        assert response.json()["user"]["email"] == "test@example.com"

    def test_authenticated_returns_correct_name(self, session_client):
        response = session_client.get("/auth/me")
        assert response.json()["user"]["name"] == "Test User"


# ---------------------------------------------------------------------------
# GET /auth/google
# ---------------------------------------------------------------------------

class TestAuthGoogle:
    def test_redirects_to_google(self, client):
        response = client.get("/auth/google", follow_redirects=False)
        assert response.status_code in (302, 307)

    def test_redirect_location_is_google_accounts(self, client):
        response = client.get("/auth/google", follow_redirects=False)
        location = response.headers["location"]
        assert "accounts.google.com" in location

    def test_redirect_includes_client_id(self, client):
        response = client.get("/auth/google", follow_redirects=False)
        assert "client_id=test-client-id" in response.headers["location"]

    def test_redirect_requests_drive_readonly_scope(self, client):
        response = client.get("/auth/google", follow_redirects=False)
        assert "drive.readonly" in response.headers["location"]

    def test_redirect_requests_offline_access(self, client):
        """access_type=offline is required to get a refresh_token."""
        response = client.get("/auth/google", follow_redirects=False)
        assert "access_type=offline" in response.headers["location"]


# ---------------------------------------------------------------------------
# GET /auth/callback
# ---------------------------------------------------------------------------

class TestAuthCallback:
    def _make_mock_http_client(self):
        """Return a mock httpx.AsyncClient that simulates Google's responses."""
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "ya29.real-access-token",
            "refresh_token": "1//refresh-token",
            "expires_in": 3600,
        }
        user_resp = MagicMock()
        user_resp.json.return_value = {
            "email": "test@example.com",
            "name": "Test User",
            "picture": "https://lh3.googleusercontent.com/photo",
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=token_resp)
        mock_client.get = AsyncMock(return_value=user_resp)
        return mock_client

    def test_redirects_to_frontend(self, client):
        mock_http = self._make_mock_http_client()
        with patch("routers.auth.httpx.AsyncClient", return_value=mock_http):
            response = client.get("/auth/callback?code=fake-code", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "localhost:5173" in response.headers["location"]

    def test_exchanges_code_with_google(self, client):
        """Verify that a POST to Google's token endpoint was made."""
        mock_http = self._make_mock_http_client()
        with patch("routers.auth.httpx.AsyncClient", return_value=mock_http):
            client.get("/auth/callback?code=fake-code", follow_redirects=False)
        mock_http.post.assert_awaited_once()
        call_args = mock_http.post.call_args
        assert "oauth2.googleapis.com/token" in call_args[0][0]


# ---------------------------------------------------------------------------
# GET /auth/logout
# ---------------------------------------------------------------------------

class TestAuthLogout:
    def test_redirects_to_frontend(self, client):
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "localhost:5173" in response.headers["location"]

    def test_clears_session_so_me_returns_401(self, session_client):
        """After logout the session cookie is invalidated; /auth/me → 401."""
        # Confirm authenticated before logout
        assert session_client.get("/auth/me").status_code == 200

        session_client.get("/auth/logout", follow_redirects=False)

        # Session cookie should be gone — /auth/me must return 401 now
        assert session_client.get("/auth/me").status_code == 401
