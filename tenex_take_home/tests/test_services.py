"""
Unit tests for helper functions in services/drive.py.

These test pure logic that does not touch HTTP or the database, so no fixtures
or mocking are needed — just call the function and assert the result.
"""

from services.drive import extract_folder_id


class TestExtractFolderId:
    """
    extract_folder_id() pulls the folder ID out of a Google Drive URL.
    The ID is the segment immediately after '/folders/' and may contain
    letters, digits, hyphens, and underscores.
    """

    def test_standard_url(self):
        url = "https://drive.google.com/drive/folders/abc123XYZ"
        assert extract_folder_id(url) == "abc123XYZ"

    def test_url_with_sharing_query_param(self):
        url = "https://drive.google.com/drive/folders/abc123?usp=sharing"
        assert extract_folder_id(url) == "abc123"

    def test_url_with_trailing_path_segment(self):
        url = "https://drive.google.com/drive/folders/abc123/view"
        assert extract_folder_id(url) == "abc123"

    def test_url_with_user_index(self):
        """Drive URLs sometimes include /u/0/ before /drive/."""
        url = "https://drive.google.com/drive/u/0/folders/abc123XYZ"
        assert extract_folder_id(url) == "abc123XYZ"

    def test_id_with_hyphens_and_underscores(self):
        url = "https://drive.google.com/drive/folders/abc-123_XYZ"
        assert extract_folder_id(url) == "abc-123_XYZ"

    def test_file_url_returns_none(self):
        """A /file/d/ URL is not a folder — must return None."""
        url = "https://drive.google.com/file/d/abc123/view"
        assert extract_folder_id(url) is None

    def test_bare_id_returns_none(self):
        """A plain string with no '/folders/' segment must return None."""
        assert extract_folder_id("abc123XYZ") is None

    def test_empty_string_returns_none(self):
        assert extract_folder_id("") is None

    def test_random_url_returns_none(self):
        assert extract_folder_id("https://example.com/abc/123") is None
