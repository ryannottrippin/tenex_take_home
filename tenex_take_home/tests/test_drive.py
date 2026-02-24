"""
Tests for GET /drive/files

This route is protected by get_current_user (Depends), so we use auth_client.
All external HTTP calls to the Google Drive API are mocked with unittest.mock
so tests are fast and never touch the network.

Mock layering:
  - httpx.AsyncClient  →  fake folder metadata + file list responses
  - fetch_all_contents →  returns [] (file parsing is tested elsewhere)
  - index_files        →  no-op (vector indexing is tested elsewhere)
"""

from unittest.mock import AsyncMock, MagicMock, patch

VALID_FOLDER_LINK = "https://drive.google.com/drive/folders/abc123xyz"
INVALID_FOLDER_LINK = "https://drive.google.com/file/d/abc123/view"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_drive_client(folder_name="Test Folder", files=None):
    """
    Build a mock httpx.AsyncClient that returns canned Drive API responses.

    The drive route makes two sequential GET calls:
      1. /drive/v3/files/{folder_id}  →  folder metadata
      2. /drive/v3/files             →  file listing

    We use side_effect to return a different MagicMock for each call.
    """
    if files is None:
        files = [{"id": "f1", "name": "notes.txt", "mimeType": "text/plain"}]

    folder_resp = MagicMock()
    folder_resp.json.return_value = {"id": "abc123xyz", "name": folder_name}

    files_resp = MagicMock()
    files_resp.json.return_value = {"files": files}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=[folder_resp, files_resp])
    return mock_client


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestDriveFilesAuth:
    def test_unauthenticated_returns_401(self, client):
        response = client.get(f"/drive/files?folder_link={VALID_FOLDER_LINK}")
        assert response.status_code == 401

    def test_unauthenticated_error_message(self, client):
        response = client.get(f"/drive/files?folder_link={VALID_FOLDER_LINK}")
        assert response.json()["error"] == "Not authenticated"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestDriveFilesValidation:
    def test_missing_folder_link_param_returns_422(self, auth_client):
        """FastAPI validates required query params and returns 422 automatically."""
        response = auth_client.get("/drive/files")
        assert response.status_code == 422

    def test_invalid_folder_link_returns_400(self, auth_client):
        response = auth_client.get("/drive/files?folder_link=not-a-drive-url")
        assert response.status_code == 400

    def test_invalid_folder_link_error_message(self, auth_client):
        response = auth_client.get("/drive/files?folder_link=not-a-drive-url")
        assert response.json()["error"] == "Invalid folder link"

    def test_file_url_treated_as_invalid(self, auth_client):
        """A file URL (/file/d/) is not a folder — must be rejected."""
        response = auth_client.get(f"/drive/files?folder_link={INVALID_FOLDER_LINK}")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Drive API errors
# ---------------------------------------------------------------------------

class TestDriveFilesApiErrors:
    def test_drive_api_error_returns_400(self, auth_client):
        """When Drive API returns an error object, the route raises AppException(400)."""
        error_resp = MagicMock()
        error_resp.json.return_value = {
            "error": {"message": "File not found", "code": 404}
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=error_resp)

        with patch("routers.drive.httpx.AsyncClient", return_value=mock_client):
            response = auth_client.get(f"/drive/files?folder_link={VALID_FOLDER_LINK}")

        assert response.status_code == 400
        assert "Drive API error" in response.json()["error"]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestDriveFilesSuccess:
    def test_returns_200(self, auth_client):
        mock_client = _make_drive_client()
        with (
            patch("routers.drive.httpx.AsyncClient", return_value=mock_client),
            patch("routers.drive.fetch_all_contents", new_callable=AsyncMock, return_value=[]),
            patch("routers.drive.index_files"),
        ):
            response = auth_client.get(f"/drive/files?folder_link={VALID_FOLDER_LINK}")
        assert response.status_code == 200

    def test_returns_folder_name(self, auth_client):
        mock_client = _make_drive_client(folder_name="My Project Docs")
        with (
            patch("routers.drive.httpx.AsyncClient", return_value=mock_client),
            patch("routers.drive.fetch_all_contents", new_callable=AsyncMock, return_value=[]),
            patch("routers.drive.index_files"),
        ):
            response = auth_client.get(f"/drive/files?folder_link={VALID_FOLDER_LINK}")
        assert response.json()["folder_name"] == "My Project Docs"

    def test_returns_file_list(self, auth_client):
        fake_files = [
            {"id": "f1", "name": "report.pdf", "mimeType": "application/pdf"},
            {"id": "f2", "name": "data.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        ]
        mock_client = _make_drive_client(files=fake_files)
        with (
            patch("routers.drive.httpx.AsyncClient", return_value=mock_client),
            patch("routers.drive.fetch_all_contents", new_callable=AsyncMock, return_value=[]),
            patch("routers.drive.index_files"),
        ):
            response = auth_client.get(f"/drive/files?folder_link={VALID_FOLDER_LINK}")
        assert response.json()["files"] == fake_files

    def test_indexing_failure_does_not_break_response(self, auth_client):
        """
        index_files is wrapped in try/except in the route.
        A ChromaDB failure (or any exception) must never block the file listing.
        """
        mock_client = _make_drive_client()

        def exploding_index(*args, **kwargs):
            raise RuntimeError("ChromaDB unavailable")

        with (
            patch("routers.drive.httpx.AsyncClient", return_value=mock_client),
            patch("routers.drive.fetch_all_contents", new_callable=AsyncMock, return_value=[]),
            patch("routers.drive.index_files", exploding_index),
        ):
            response = auth_client.get(f"/drive/files?folder_link={VALID_FOLDER_LINK}")

        assert response.status_code == 200
