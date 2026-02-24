"""
Tests for Pydantic request schemas (schemas/chat.py).

These are pure unit tests — no HTTP, no TestClient.  Pydantic raises
ValidationError for bad input, which we verify directly.
"""

import pytest
from pydantic import ValidationError

from schemas.chat import ChatRequest, HistoryMessage


# ---------------------------------------------------------------------------
# HistoryMessage
# ---------------------------------------------------------------------------

class TestHistoryMessage:
    def test_valid_user_message(self):
        msg = HistoryMessage(role="user", text="hello")
        assert msg.role == "user"
        assert msg.text == "hello"

    def test_valid_assistant_message(self):
        msg = HistoryMessage(role="assistant", text="here is the answer")
        assert msg.role == "assistant"

    def test_missing_role_raises(self):
        with pytest.raises(ValidationError):
            HistoryMessage(text="hello")

    def test_missing_text_raises(self):
        with pytest.raises(ValidationError):
            HistoryMessage(role="user")


# ---------------------------------------------------------------------------
# ChatRequest
# ---------------------------------------------------------------------------

class TestChatRequest:
    def test_valid_minimal(self):
        req = ChatRequest(
            folder_link="https://drive.google.com/drive/folders/abc123",
            message="What is this folder about?",
        )
        assert req.folder_link == "https://drive.google.com/drive/folders/abc123"
        assert req.message == "What is this folder about?"

    def test_history_defaults_to_empty_list(self):
        req = ChatRequest(folder_link="https://...", message="hi")
        assert req.history == []

    def test_missing_folder_link_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="hi")

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(folder_link="https://...")

    def test_valid_with_history(self):
        req = ChatRequest(
            folder_link="https://drive.google.com/drive/folders/abc",
            message="follow up question",
            history=[
                {"role": "user", "text": "first question"},
                {"role": "assistant", "text": "first answer"},
            ],
        )
        assert len(req.history) == 2
        assert isinstance(req.history[0], HistoryMessage)
        assert req.history[0].role == "user"
        assert req.history[1].role == "assistant"

    def test_history_with_invalid_entry_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(
                folder_link="https://...",
                message="hi",
                history=[{"role": "user"}],  # missing 'text'
            )
