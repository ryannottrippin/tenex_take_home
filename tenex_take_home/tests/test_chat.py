"""
Tests for POST /chat

The chat route has two retrieval paths:
  • RAG path  — vector search (search()) returns chunks → passed to Claude
  • Fallback  — search() returns [] → full file text pulled from _folder_cache

Both paths then call the Anthropic SDK.  All external calls are mocked.

Mock layering (in order of execution inside the route):
  search()                →  MagicMock (runs via asyncio.to_thread)
  anthropic.Anthropic()   →  MagicMock with .messages.create returning a fake response
  httpx.AsyncClient       →  only needed on the fallback cache-miss path
  index_files()           →  MagicMock (only called on fallback cache-miss)
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

VALID_FOLDER_LINK = "https://drive.google.com/drive/folders/abc123xyz"
FOLDER_ID = "abc123xyz"

CHAT_BODY = {
    "folder_link": VALID_FOLDER_LINK,
    "message": "What does the document say?",
    "history": [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claude_mock(answer: str = "Here is the answer."):
    """Return a mock Anthropic client whose messages.create returns `answer`."""
    content_block = MagicMock()
    content_block.text = answer

    message = MagicMock()
    message.content = [content_block]

    mock_anthropic = MagicMock()
    mock_anthropic.return_value.messages.create.return_value = message
    return mock_anthropic


FAKE_CHUNKS = [
    {
        "file_id": "f1",
        "file_name": "report.pdf",
        "passage": "The quarterly revenue was $10M.",
        "page_label": "p. 3",
    },
    {
        "file_id": "f2",
        "file_name": "summary.docx",
        "passage": "Key takeaways from the meeting.",
        "page_label": None,
    },
]

FAKE_CACHE_FILES = [
    {
        "id": "f1",
        "name": "report.pdf",
        "mimeType": "application/pdf",
        "content": "The quarterly revenue was $10M.",
    }
]


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestChatAuth:
    def test_unauthenticated_returns_401(self, client):
        response = client.post("/chat", json=CHAT_BODY)
        assert response.status_code == 401

    def test_unauthenticated_error_key(self, client):
        response = client.post("/chat", json=CHAT_BODY)
        assert "error" in response.json()


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestChatValidation:
    def test_missing_message_returns_422(self, auth_client):
        """Pydantic rejects the request before the route handler runs."""
        response = auth_client.post("/chat", json={
            "folder_link": VALID_FOLDER_LINK,
        })
        assert response.status_code == 422

    def test_missing_folder_link_returns_422(self, auth_client):
        response = auth_client.post("/chat", json={"message": "hi"})
        assert response.status_code == 422

    def test_invalid_folder_link_returns_400(self, auth_client):
        response = auth_client.post("/chat", json={
            "folder_link": "not-a-drive-link",
            "message": "hi",
        })
        assert response.status_code == 400
        assert response.json()["error"] == "Invalid folder link"


# ---------------------------------------------------------------------------
# RAG path — vector search returns chunks
# ---------------------------------------------------------------------------

class TestChatRagPath:
    def test_returns_200(self, auth_client):
        mock_anthropic = _make_claude_mock()
        with (
            patch("routers.chat.search", MagicMock(return_value=FAKE_CHUNKS)),
            patch("routers.chat.anthropic.Anthropic", mock_anthropic),
        ):
            response = auth_client.post("/chat", json=CHAT_BODY)
        assert response.status_code == 200

    def test_returns_answer_field(self, auth_client):
        mock_anthropic = _make_claude_mock("Revenue grew by 20%.")
        with (
            patch("routers.chat.search", MagicMock(return_value=FAKE_CHUNKS)),
            patch("routers.chat.anthropic.Anthropic", mock_anthropic),
        ):
            response = auth_client.post("/chat", json=CHAT_BODY)
        assert response.json()["answer"] == "Revenue grew by 20%."

    def test_citations_are_deduplicated_by_file(self, auth_client):
        """
        Two chunks from the same file should produce only one citation.
        """
        chunks_with_duplicate = [
            {"file_id": "f1", "file_name": "report.pdf", "passage": "chunk A", "page_label": "p. 1"},
            {"file_id": "f1", "file_name": "report.pdf", "passage": "chunk B", "page_label": "p. 2"},
        ]
        mock_anthropic = _make_claude_mock()
        with (
            patch("routers.chat.search", MagicMock(return_value=chunks_with_duplicate)),
            patch("routers.chat.anthropic.Anthropic", mock_anthropic),
        ):
            response = auth_client.post("/chat", json=CHAT_BODY)
        citations = response.json()["citations"]
        assert len(citations) == 1
        assert citations[0]["id"] == "f1"

    def test_citation_includes_passage(self, auth_client):
        mock_anthropic = _make_claude_mock()
        with (
            patch("routers.chat.search", MagicMock(return_value=FAKE_CHUNKS)),
            patch("routers.chat.anthropic.Anthropic", mock_anthropic),
        ):
            response = auth_client.post("/chat", json=CHAT_BODY)
        first_citation = response.json()["citations"][0]
        assert "passage" in first_citation
        assert first_citation["passage"] == FAKE_CHUNKS[0]["passage"]

    def test_citation_includes_page_label(self, auth_client):
        mock_anthropic = _make_claude_mock()
        with (
            patch("routers.chat.search", MagicMock(return_value=FAKE_CHUNKS)),
            patch("routers.chat.anthropic.Anthropic", mock_anthropic),
        ):
            response = auth_client.post("/chat", json=CHAT_BODY)
        first_citation = response.json()["citations"][0]
        assert first_citation["page_label"] == "p. 3"

    def test_history_is_forwarded_to_claude(self, auth_client):
        """Previous conversation turns must be passed to messages.create."""
        mock_anthropic = _make_claude_mock()
        body = {
            **CHAT_BODY,
            "history": [
                {"role": "user", "text": "earlier question"},
                {"role": "assistant", "text": "earlier answer"},
            ],
        }
        with (
            patch("routers.chat.search", MagicMock(return_value=FAKE_CHUNKS)),
            patch("routers.chat.anthropic.Anthropic", mock_anthropic),
        ):
            auth_client.post("/chat", json=body)

        create_call = mock_anthropic.return_value.messages.create
        create_call.assert_called_once()
        messages_arg = create_call.call_args.kwargs["messages"]
        # history (2) + current user message (1) = 3
        assert len(messages_arg) == 3
        assert messages_arg[0]["role"] == "user"
        assert messages_arg[0]["content"] == "earlier question"


# ---------------------------------------------------------------------------
# Fallback path — search returns no chunks, use cache
# ---------------------------------------------------------------------------

class TestChatFallbackPath:
    def _populate_cache(self):
        from services.drive import FolderCache, _folder_cache
        _folder_cache[("test@example.com", FOLDER_ID)] = FolderCache(
            files=FAKE_CACHE_FILES,
            fetched_at=time.time(),
        )

    def test_falls_back_to_cache_when_no_chunks(self, auth_client):
        self._populate_cache()
        mock_anthropic = _make_claude_mock("Based on the report…")
        with (
            patch("routers.chat.search", MagicMock(return_value=[])),
            patch("routers.chat.anthropic.Anthropic", mock_anthropic),
        ):
            response = auth_client.post("/chat", json=CHAT_BODY)
        assert response.status_code == 200
        assert response.json()["answer"] == "Based on the report…"

    def test_fallback_citations_match_mentioned_files(self, auth_client):
        """
        On the fallback path, citations are built by name-matching: a file is
        cited if its name appears in the answer text.
        """
        self._populate_cache()
        # Claude answer mentions the file name
        mock_anthropic = _make_claude_mock("According to report.pdf the revenue grew.")
        with (
            patch("routers.chat.search", MagicMock(return_value=[])),
            patch("routers.chat.anthropic.Anthropic", mock_anthropic),
        ):
            response = auth_client.post("/chat", json=CHAT_BODY)
        citations = response.json()["citations"]
        assert any(c["name"] == "report.pdf" for c in citations)


# ---------------------------------------------------------------------------
# Error handling — Claude API failures
# ---------------------------------------------------------------------------

class TestChatErrorHandling:
    def _with_overloaded_claude(self):
        """Return patches that make Claude raise a 529 APIStatusError."""
        mock_response = httpx.Response(
            status_code=529,
            request=httpx.Request("POST", "https://api.anthropic.com"),
        )
        import anthropic
        exc = anthropic.APIStatusError(
            "Overloaded",
            response=mock_response,
            body={"error": {"type": "overloaded_error"}},
        )
        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.side_effect = exc
        return mock_anthropic

    def test_claude_overloaded_returns_503(self, auth_client):
        """HTTP 529 from Anthropic must be surfaced as HTTP 503."""
        from services.drive import FolderCache, _folder_cache
        _folder_cache[("test@example.com", FOLDER_ID)] = FolderCache(
            files=FAKE_CACHE_FILES, fetched_at=time.time()
        )
        mock_anthropic = self._with_overloaded_claude()
        with (
            patch("routers.chat.search", MagicMock(return_value=[])),
            patch("routers.chat.anthropic.Anthropic", mock_anthropic),
        ):
            response = auth_client.post("/chat", json=CHAT_BODY)
        assert response.status_code == 503

    def test_claude_overloaded_returns_friendly_message(self, auth_client):
        """The user-facing error must mention 'unavailable', not expose raw SDK text."""
        from services.drive import FolderCache, _folder_cache
        _folder_cache[("test@example.com", FOLDER_ID)] = FolderCache(
            files=FAKE_CACHE_FILES, fetched_at=time.time()
        )
        mock_anthropic = self._with_overloaded_claude()
        with (
            patch("routers.chat.search", MagicMock(return_value=[])),
            patch("routers.chat.anthropic.Anthropic", mock_anthropic),
        ):
            response = auth_client.post("/chat", json=CHAT_BODY)
        assert "unavailable" in response.json()["error"].lower()
