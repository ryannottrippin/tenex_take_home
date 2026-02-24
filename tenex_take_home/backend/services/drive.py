import re
import time
from dataclasses import dataclass, field

import httpx

from core.config import settings

CACHE_TTL = 600  # seconds before cached file contents expire


@dataclass
class FolderCache:
    files: list[dict] = field(default_factory=list)
    fetched_at: float = 0.0


# keyed by (user_email, folder_id)
_folder_cache: dict[tuple[str, str], FolderCache] = {}


def extract_folder_id(folder_link: str) -> str | None:
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_link)
    return match.group(1) if match else None


async def get_access_token(request, client: httpx.AsyncClient) -> str:
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
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
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
