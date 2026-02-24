import asyncio
import time

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from core.dependencies import get_current_user
from core.exceptions import AppException
from services.drive import (
    CACHE_TTL, FolderCache, _folder_cache,
    extract_folder_id, get_access_token, list_drive_files,
)
from parsers import fetch_all_contents
from vectorstore import index_files

router = APIRouter(prefix="/drive")


@router.get("/files")
async def drive_files(
    request: Request,
    folder_link: str,
    user: dict = Depends(get_current_user),
):
    folder_id = extract_folder_id(folder_link)
    if not folder_id:
        raise AppException(400, "Invalid folder link")

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
            raise AppException(
                400,
                f"Drive API error: {folder_data['error'].get('message', 'unknown')}",
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
