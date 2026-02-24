"""
Tests for AppException and its global exception handler.

Two things matter here:
1. AppException is a plain Python exception that stores status_code + detail.
2. The handler registered in main.py returns {"error": detail} — NOT {"detail": detail}.
   The frontend's apiFetch checks `if (data.error)`, so this key name is a contract.
"""

from core.exceptions import AppException


# ---------------------------------------------------------------------------
# Unit tests — AppException class itself
# ---------------------------------------------------------------------------

class TestAppException:
    def test_stores_status_code(self):
        exc = AppException(404, "not found")
        assert exc.status_code == 404

    def test_stores_detail(self):
        exc = AppException(400, "bad request")
        assert exc.detail == "bad request"

    def test_is_subclass_of_exception(self):
        exc = AppException(500, "server error")
        assert isinstance(exc, Exception)

    def test_different_status_codes(self):
        for code in (400, 401, 403, 404, 422, 500, 503):
            exc = AppException(code, "message")
            assert exc.status_code == code


# ---------------------------------------------------------------------------
# Integration tests — handler registered on the main FastAPI app
# ---------------------------------------------------------------------------

class TestExceptionHandlerIntegration:
    def test_401_uses_error_key_not_detail(self, client):
        """
        The frontend apiFetch checks `data.error`, not `data.detail`.
        Any AppException must come back with the 'error' key.
        """
        response = client.get("/drive/files?folder_link=" + "https://drive.google.com/drive/folders/abc")
        assert response.status_code == 401
        body = response.json()
        assert "error" in body
        assert "detail" not in body

    def test_401_error_value_is_string(self, client):
        response = client.get("/drive/files?folder_link=https://drive.google.com/drive/folders/abc")
        assert isinstance(response.json()["error"], str)

    def test_400_bad_folder_link_preserves_status_code(self, auth_client):
        """AppException(400) must produce HTTP 400, not 200 or 500."""
        response = auth_client.get("/drive/files?folder_link=not-a-url-at-all")
        assert response.status_code == 400

    def test_400_bad_folder_link_error_message(self, auth_client):
        response = auth_client.get("/drive/files?folder_link=not-a-url-at-all")
        assert response.json()["error"] == "Invalid folder link"
