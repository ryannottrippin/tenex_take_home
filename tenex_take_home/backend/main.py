import asyncio
import os
import re
import time
from dataclasses import dataclass, field

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import anthropic

from parsers import fetch_all_contents
from vectorstore import index_files, search

load_dotenv()

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

CACHE_TTL = 600  # seconds before cached file contents expire


@dataclass
class FolderCache:
    files: list[dict] = field(default_factory=list)
    fetched_at: float = 0.0


# keyed by (user_email, folder_id)
_folder_cache: dict[tuple[str, str], FolderCache] = {}


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)


def extract_folder_id(folder_link: str) -> str | None:
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_link)
    return match.group(1) if match else None


async def get_access_token(request: Request, client: httpx.AsyncClient) -> str:
    """Return a valid access token, refreshing it if it has expired."""
    expiry = request.session.get("token_expiry", 0)
    if time.time() < expiry - 60:
        return request.session["access_token"]

    refresh_token = request.session.get("refresh_token")
    if not refresh_token:
        return request.session.get("access_token", "")

    response = await client.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    tokens = response.json()

    if "access_token" in tokens:
        request.session["access_token"] = tokens["access_token"]
        request.session["token_expiry"] = time.time() + tokens.get("expires_in", 3600)
        return tokens["access_token"]

    return request.session.get("access_token", "")


async def list_drive_files(
    client: httpx.AsyncClient, folder_id: str, access_token: str
) -> list[dict]:
    """List all non-trashed files in a Drive folder."""
    response = await client.get(
        "https://www.googleapis.com/drive/v3/files",
        params={
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "files(id,name,mimeType)",
            "pageSize": 100,
            "orderBy": "name",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return response.json().get("files", [])


# ===== AUTH =====

@app.get("/auth/google")
def auth_google():
    scope = " ".join(SCOPES)
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        "&response_type=code"
        f"&scope={scope}"
        "&access_type=offline"
        "&prompt=consent"
    )
    return RedirectResponse(url)


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str):
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        tokens = token_response.json()

        user_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        user = user_response.json()

    request.session["user"] = {
        "email": user["email"],
        "name": user.get("name", ""),
        "picture": user.get("picture", ""),
    }
    request.session["access_token"] = tokens["access_token"]
    request.session["refresh_token"] = tokens.get("refresh_token", "")
    request.session["token_expiry"] = time.time() + tokens.get("expires_in", 3600)

    return RedirectResponse("http://localhost:5173")


@app.get("/auth/me")
def auth_me(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"user": None}, status_code=401)
    return JSONResponse({"user": user})


@app.get("/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse("http://localhost:5173")


# ===== DRIVE =====

@app.get("/drive/files")
async def drive_files(request: Request, folder_link: str):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    folder_id = extract_folder_id(folder_link)
    if not folder_id:
        return JSONResponse({"error": "Invalid folder link"}, status_code=400)

    async with httpx.AsyncClient() as client:
        access_token = await get_access_token(request, client)
        headers = {"Authorization": f"Bearer {access_token}"}

        folder_response = await client.get(
            f"https://www.googleapis.com/drive/v3/files/{folder_id}",
            params={"fields": "id,name", "supportsAllDrives": "true"},
            headers=headers,
        )
        folder_data = folder_response.json()

        if "error" in folder_data:
            return JSONResponse(
                {"error": f"Drive API error: {folder_data['error'].get('message', 'unknown')}"},
                status_code=400,
            )

        files = await list_drive_files(client, folder_id, access_token)
        contents = await fetch_all_contents(client, files, access_token)
        _folder_cache[(user["email"], folder_id)] = FolderCache(
            files=contents, fetched_at=time.time()
        )

    try:
        await asyncio.to_thread(index_files, user["email"], folder_id, contents)
    except Exception:
        pass  # indexing failure must not break file listing

    return JSONResponse({
        "folder_name": folder_data.get("name", "Folder"),
        "files": files,
    })


# ===== CHAT =====

@app.post("/chat")
async def chat(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "Anthropic API key not configured"}, status_code=500)

    body = await request.json()
    folder_link = body.get("folder_link", "")
    message = body.get("message", "")
    history = body.get("history", [])

    folder_id = extract_folder_id(folder_link)
    if not folder_id:
        return JSONResponse({"error": "Invalid folder link"}, status_code=400)

    # Try vector search first; fall back to full context stuffing if unavailable
    chunks = await asyncio.to_thread(search, user["email"], folder_id, message)

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
        {"role": msg["role"], "content": msg["text"]}
        for msg in history
    ]
    claude_messages.append({"role": "user", "content": message})

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system_prompt,
            messages=claude_messages,
        )
    except anthropic.APIStatusError as e:
        if e.status_code == 529:
            return JSONResponse(
                {"error": "The AI service is temporarily unavailable due to high demand. Please try again in a moment."},
                status_code=503,
            )
        return JSONResponse({"error": f"Claude API error: {str(e)[:200]}"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": f"Claude API error: {str(e)[:200]}"}, status_code=500)

    answer = response.content[0].text

    if chunks:
        # Deduplicate citations by file, include the passage that was retrieved
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
