# Full Stack Best Practices: FastAPI + Uvicorn + React

> A concise reference guide for building robust, scalable, and maintainable full stack applications.

---

## 1. Structure Your FastAPI Project for Scalability

Avoid dumping everything into `main.py`. Use a modular layout that separates concerns clearly:

```
backend/
├── app/
│   ├── main.py           # App entry point, middleware registration
│   ├── core/             # Config, security, dependencies
│   ├── api/
│   │   └── v1/           # Versioned routers
│   │       ├── routes/
│   │       └── __init__.py
│   ├── models/           # SQLAlchemy / Pydantic models
│   ├── schemas/          # Request/response schemas
│   ├── services/         # Business logic layer
│   └── db/               # Database session, migrations
frontend/
├── src/
│   ├── api/              # Axios/fetch wrappers
│   ├── components/
│   ├── pages/
│   ├── hooks/
│   └── store/            # State management
```

Keep business logic in `services/`, not in route handlers. Routes should only handle HTTP concerns.

---

## 2. Use Pydantic v2 Schemas Rigorously for Validation

Never trust raw input. Define strict Pydantic schemas for every request and response, and keep them separate from your ORM models:

```python
# schemas/user.py
from pydantic import BaseModel, EmailStr, field_validator

class UserCreate(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

class UserResponse(BaseModel):
    id: int
    email: EmailStr

    model_config = {"from_attributes": True}  # replaces orm_mode in Pydantic v2
```

Use `response_model=UserResponse` on every route to prevent accidental data leakage.

---

## 3. Configure Uvicorn and FastAPI for Production Correctly

Never run Uvicorn with `--reload` in production. Use a process manager like `gunicorn` with the Uvicorn worker class, and configure workers based on CPU count:

```bash
# Production startup
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
```

In `main.py`, set environment-aware settings:

```python
app = FastAPI(
    title="My API",
    docs_url="/docs" if settings.DEBUG else None,   # Hide docs in prod
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)
```

---

## 4. Implement Middleware Thoughtfully and in the Right Order

Middleware order in FastAPI/Starlette matters — it executes in reverse registration order. Structure it intentionally:

```python
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

# Register outermost (last to execute on request) first
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # Never use ["*"] in production
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

Write custom middleware for cross-cutting concerns like request logging, correlation IDs, and rate limiting — not inside route handlers.

---

## 5. Handle Authentication with JWT + Dependency Injection

Use FastAPI's dependency injection system for clean, reusable auth guards. Never roll your own crypto — use `python-jose` and `passlib`:

```python
# core/security.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return await user_service.get_by_id(db, int(user_id))

# Usage in routes
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
```

On the React side, store tokens in `httpOnly` cookies, not `localStorage`, to prevent XSS theft.

---

## 6. Use Async SQLAlchemy and Manage DB Sessions via Dependency Injection

Always use `async`/`await` with your database layer to avoid blocking Uvicorn's event loop. Use `AsyncSession` and never share sessions across requests:

```python
# db/session.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

Use Alembic for all schema migrations — never use `create_all()` in production.

---

## 7. Centralize Error Handling with Custom Exception Handlers

Avoid scattering `try/except` blocks across routes. Define domain exceptions and register global handlers:

```python
# core/exceptions.py
class AppException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail

class ResourceNotFound(AppException):
    def __init__(self, resource: str):
        super().__init__(404, f"{resource} not found")

# main.py
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
```

On the React side, create a centralized API client (Axios interceptor or `fetch` wrapper) that catches and normalizes errors before they reach your components.

---

## 8. Build a Typed, Centralized API Layer in React

Never write raw `fetch` calls scattered throughout components. Create a typed API client that all components consume:

```typescript
// src/api/client.ts
import axios from "axios";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  withCredentials: true,
});

apiClient.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401) {
      // redirect to login or refresh token
    }
    return Promise.reject(error);
  }
);

export default apiClient;

// src/api/users.ts
import apiClient from "./client";
import type { User } from "../types";

export const getMe = (): Promise<User> =>
  apiClient.get("/api/v1/users/me").then((r) => r.data);
```

Pair this with React Query (`@tanstack/react-query`) to handle caching, loading states, and refetching declaratively.

---

## 9. Manage Configuration Securely with Pydantic Settings

Never hardcode secrets or environment-specific values. Use `pydantic-settings` for type-safe, validated configuration loaded from environment variables:

```python
# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "MyApp"
    DEBUG: bool = False
    DATABASE_URL: str
    SECRET_KEY: str
    ALLOWED_ORIGINS: list[str] = []
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

settings = Settings()
```

Use a `.env` file locally and inject real secrets via environment variables or a secrets manager (AWS Secrets Manager, HashiCorp Vault) in production. Never commit `.env` to source control.

---

## 10. Implement Structured Logging, Health Checks, and Observability

Log structured JSON, not plain strings. Use `structlog` or configure Python's `logging` with a JSON formatter so logs are parseable by tools like Datadog or CloudWatch:

```python
# core/logging.py
import logging, json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": self.formatTime(record),
        })
```

Always expose a `/health` endpoint for load balancers and orchestrators:

```python
@app.get("/health", tags=["ops"])
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "db": "connected"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")
```

Add request ID middleware so every log line across the backend can be traced to a single frontend request, making debugging in production dramatically easier.

---

*Following these ten practices will produce a codebase that is secure, observable, easy to test, and ready to scale.*
