import asyncio
import time

import anthropic
import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from core.config import settings
from core.dependencies import get_current_user
from core.exceptions import AppException
from schemas.chat import ChatRequest
from services.drive import (
    CACHE_TTL, FolderCache, _folder_cache,
    extract_folder_id, get_access_token, list_drive_files,
)
from parsers import fetch_all_contents
from vectorstore import index_files, search

router = APIRouter()


@router.post("/chat")
async def chat(
    request: Request,
    body: ChatRequest,
    user: dict = Depends(get_current_user),
):
    folder_id = extract_folder_id(body.folder_link)
    if not folder_id:
        raise AppException(400, "Invalid folder link")

    # Try vector search first; fall back to full context stuffing if unavailable
    chunks = await asyncio.to_thread(search, user["email"], folder_id, body.message)

    if chunks:
        def _chunk_header(c):
            loc = f" ({c['page_label']})" if c.get("page_label") else ""
            return f"=== {c['file_name']}{loc} ===\n{c['passage']}"
        context = "\n\n".join(_chunk_header(c) for c in chunks)
        system_prompt = (
            "You are a helpful assistant answering questions about documents in a Google Drive folder. "
            "Use the relevant passages below to answer the user's question. "
            "When you reference information from a specific file, mention the file name. "
            "Be concise and accurate. "
            "Respond in plain text only — no markdown, no headers, no bullet symbols, no bold or italic markers.\n\n"
            f"Relevant passages:\n\n{context}"
        )
        file_contents = []
    else:
        # Fall back to full context stuffing (no vector index yet or empty folder)
        cache_entry = _folder_cache.get((user["email"], folder_id))
        if cache_entry and time.time() - cache_entry.fetched_at < CACHE_TTL:
            file_contents = cache_entry.files
        else:
            async with httpx.AsyncClient() as client:
                access_token = await get_access_token(request, client)
                files = await list_drive_files(client, folder_id, access_token)
                file_contents = await fetch_all_contents(client, files, access_token)
                _folder_cache[(user["email"], folder_id)] = FolderCache(
                    files=file_contents, fetched_at=time.time()
                )
                try:
                    await asyncio.to_thread(index_files, user["email"], folder_id, file_contents)
                except Exception:
                    pass

        if file_contents:
            context = "\n\n".join(
                f"=== {fc['name']} ===\n{fc['content']}" for fc in file_contents
            )
            system_prompt = (
                "You are a helpful assistant answering questions about documents in a Google Drive folder. "
                "Use the file contents below to answer the user's question. "
                "When you reference information from a specific file, mention the file name. "
                "Be concise and accurate. "
                "Respond in plain text only — no markdown, no headers, no bullet symbols, no bold or italic markers.\n\n"
                f"File contents:\n\n{context}"
            )
        else:
            system_prompt = (
                "You are a helpful assistant. The connected Google Drive folder contains no readable text files. "
                "Let the user know and suggest they try a folder with Google Docs or plain text files."
            )

    claude_messages = [
        {"role": msg.role, "content": msg.text}
        for msg in body.history
    ]
    claude_messages.append({"role": "user", "content": body.message})

    try:
        ai_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = ai_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system_prompt,
            messages=claude_messages,
        )
    except anthropic.APIStatusError as e:
        if e.status_code == 529:
            raise AppException(
                503,
                "The AI service is temporarily unavailable due to high demand. Please try again in a moment.",
            )
        raise AppException(500, f"Claude API error: {str(e)[:200]}")
    except Exception as e:
        raise AppException(500, f"Claude API error: {str(e)[:200]}")

    answer = response.content[0].text

    if chunks:
        seen: set[str] = set()
        citations = []
        for c in chunks:
            if c["file_id"] not in seen:
                seen.add(c["file_id"])
                citations.append({
                    "name": c["file_name"],
                    "id": c["file_id"],
                    "passage": c["passage"],
                    "page_label": c.get("page_label"),
                })
    else:
        citations = [
            {"name": fc["name"], "id": fc["id"]}
            for fc in file_contents
            if fc["name"].lower() in answer.lower()
        ]

    return JSONResponse({"answer": answer, "citations": citations})
