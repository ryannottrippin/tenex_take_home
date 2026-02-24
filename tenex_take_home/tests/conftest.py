"""
Shared fixtures for all route tests.

Boot order matters: os.environ must be populated BEFORE importing anything from
the backend, because `core/config.py` runs `Settings()` at module level and
reads env vars at that moment.  Even if a real `.env` exists, env vars take
precedence over the file, so these test values always win.
"""

import base64
import json
import os

# ── Must come before any backend import ──────────────────────────────────────
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-key")
# ─────────────────────────────────────────────────────────────────────────────

import itsdangerous
import pytest
from starlette.testclient import TestClient

from core.dependencies import get_current_user
from main import app

# ---------------------------------------------------------------------------
# Constants shared across test modules
# ---------------------------------------------------------------------------

TEST_USER = {"email": "test@example.com", "name": "Test User", "picture": ""}
SESSION_SECRET = os.environ["SESSION_SECRET"]
VALID_FOLDER_LINK = "https://drive.google.com/drive/folders/abc123xyz"
FOLDER_ID = "abc123xyz"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session_cookie(data: dict) -> str:
    """
    Build a signed Starlette session cookie value that SessionMiddleware will
    accept.

    Starlette's SessionMiddleware stores sessions as:
        TimestampSigner(secret).sign(base64(json(data)))

    We replicate that here so tests can inject a pre-authenticated session
    without going through the real OAuth flow.
    """
    payload = base64.b64encode(json.dumps(data).encode("utf-8"))
    signer = itsdangerous.TimestampSigner(SESSION_SECRET)
    return signer.sign(payload).decode("utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Unauthenticated test client — no session cookie attached."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth_client():
    """
    Client whose get_current_user dependency is overridden to return TEST_USER.

    Use this for routes protected by ``Depends(get_current_user)`` (/drive/files,
    /chat).  The override is cleared after the test so it cannot leak into other
    test functions.
    """
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def session_client():
    """
    Client with a real signed Starlette session cookie.

    Use this for routes that read ``request.session`` directly rather than using
    the ``get_current_user`` dependency — specifically /auth/me and /auth/logout.
    """
    session_data = {
        "user": TEST_USER,
        "access_token": "fake-access-token",
        "token_expiry": 9_999_999_999.0,  # far future — never expired
        "refresh_token": "",
    }
    cookie_value = make_session_cookie(session_data)
    with TestClient(app, raise_server_exceptions=False) as c:
        c.cookies.set("session", cookie_value, domain="testserver", path="/")
        yield c


@pytest.fixture(autouse=True)
def clear_folder_cache():
    """
    Clear the shared in-memory folder cache before and after every test.

    The cache is a module-level singleton dict in services/drive.py.  Without
    this fixture, state written by one test (e.g. a populated cache entry) would
    bleed into subsequent tests.
    """
    from services.drive import _folder_cache
    _folder_cache.clear()
    yield
    _folder_cache.clear()
