from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from core.config import settings
from core.exceptions import AppException, app_exception_handler
from routers import auth, drive, chat

app = FastAPI(
    title="DriveChat API",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET)

app.add_exception_handler(AppException, app_exception_handler)

app.include_router(auth.router)
app.include_router(drive.router)
app.include_router(chat.router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
