from pydantic import BaseModel


class HistoryMessage(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    folder_link: str
    message: str
    history: list[HistoryMessage] = []
