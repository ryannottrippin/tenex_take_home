import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from core.config import settings

router = APIRouter(prefix="/auth")

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


@router.get("/google")
def auth_google():
    scope = " ".join(SCOPES)
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
        "&response_type=code"
        f"&scope={scope}"
        "&access_type=offline"
        "&prompt=consent"
    )
    return RedirectResponse(url)


@router.get("/callback")
async def auth_callback(request: Request, code: str):
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
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


@router.get("/me")
def auth_me(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"user": None}, status_code=401)
    return JSONResponse({"user": user})


@router.get("/logout")
def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse("http://localhost:5173")
