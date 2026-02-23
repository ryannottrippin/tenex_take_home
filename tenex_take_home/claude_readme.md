# Claude Notes

## User Background
- Knows JavaScript and Python
- Familiar with FastAPI + Uvicorn
- Learning React for the first time
- Prefers to build one screen at a time — don't get ahead
- Using conda for Python environments

## Project Status
**Fully working end-to-end.** All three screens complete, auth + Drive + chat + RAG all confirmed working.
Page-aware citations (page numbers for PDFs, slide numbers for .pptx) are implemented and working.

## Project Goal
A web interface where users:
1. Sign in with Google (OAuth)
2. Paste a Google Drive folder link
3. Have an AI-powered conversation about the files in that folder, with citations

---

## Stack
- **Frontend:** React 18 + Vite (port 5173)
- **Backend:** FastAPI + Uvicorn (port 8000)
- **Auth:** Google OAuth 2.0 — fully wired end to end
- **AI:** Anthropic Claude (`claude-haiku-4-5-20251001`) via `anthropic` SDK — key is set in .env
- **Vector search:** ChromaDB (local, persists to `backend/chroma_db/`) + Google `text-embedding-004`

---

## Frontend

### File Structure
```
frontend/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── main.jsx          # Entry point, mounts React, imports CSS
    ├── App.jsx           # Screen router using useState + useEffect
    ├── index.css         # All styles (single file, CSS variables)
    └── components/
        ├── AuthScreen.jsx    # Screen 1: COMPLETE — sign in with Google
        ├── DriveInput.jsx    # Screen 2: COMPLETE — paste Drive folder link
        └── ChatInterface.jsx # Screen 3: COMPLETE — sidebar + messages + input
```

### Screen Routing (App.jsx)
- Starts in `'loading'` state, calls `GET /auth/me` on mount
- If user session exists → goes to `'drive'` screen
- If no session → goes to `'auth'` screen
- States: `'loading'` | `'auth'` | `'drive'` | `'chat'`
- No React Router — just conditional rendering with `if` statements
- `user` object (email, name, picture) passed as prop to DriveInput and ChatInterface
- `folderLink` state passed from DriveInput → ChatInterface

### AuthScreen.jsx — COMPLETE
- "Continue with Google" button does `window.location.href = 'http://localhost:8000/auth/google'`
- Full-page redirect to backend, which kicks off the OAuth flow

### DriveInput.jsx — COMPLETE
- Receives `user` prop from App.jsx (real email/name from Google session)
- Displays user email and initials in navbar
- Input field for pasting a Google Drive folder link
- On submit → calls `onSubmit(link)` which transitions App to `'chat'` screen

### ChatInterface.jsx — COMPLETE
- Receives `user` and `folderLink` props from App.jsx
- On mount: calls `GET /drive/files?folder_link=...`, populates sidebar with file list and folder name
- Sidebar: brand header, folder name, file list with icons, user email at bottom
- Main area: message thread (user right / assistant left), "Thinking..." indicator while waiting
- Citations render as clickable `<a>` pill badges opening `https://drive.google.com/file/d/{id}/view` in a new tab
- Citation pills show page/slide label when available: e.g. `filename.pdf (p. 3)` or `deck.pptx (Slide 7)`
- If RAG is active, a "View source passages" `<details>` expander shows the exact retrieved chunk under each response, with file name and page label header
- Input bar: textarea, Enter to send (Shift+Enter for newline), auto-scrolls to latest message
- Calls `POST /chat` on send, passes full conversation history

---

## Backend — COMPLETE

### File Structure
```
backend/
├── main.py          # FastAPI app — auth + drive + chat endpoints
├── parsers.py       # File content extraction (all MIME types + fetch_all_contents)
├── vectorstore.py   # ChromaDB + Google embedding — index_files, search
├── requirements.txt # Python dependencies
├── .env             # Secrets (not committed)
├── chroma_db/       # Persisted vector index (not committed)
└── .gitignore
```

### Running the backend
```bash
conda activate <your-env>
cd backend
uvicorn main:app --reload --port 8000
```

### Environment Variables (.env)
- `GOOGLE_CLIENT_ID` — from Google Cloud Console
- `GOOGLE_CLIENT_SECRET` — from Google Cloud Console
- `GOOGLE_REDIRECT_URI` — `http://localhost:8000/auth/callback`
- `SESSION_SECRET` — random string, signs session cookies
- `ANTHROPIC_API_KEY` — Claude API key
- `GOOGLE_API_KEY` — from Google AI Studio, used for `text-embedding-004`

### Middleware
1. **CORSMiddleware** — allows React (port 5173) to call backend (port 8000)
2. **SessionMiddleware** — stores user + access_token in a signed cookie

### Auth Endpoints

**GET /auth/google**
- Builds Google OAuth URL and redirects there
- Scopes: drive.readonly, userinfo.email, userinfo.profile

**GET /auth/callback?code=...**
- Exchanges code for tokens, fetches user info, stores in session
- Saves `refresh_token` and `token_expiry` (unix timestamp) for auto-refresh
- Redirects to http://localhost:5173

**GET /auth/me**
- Returns session user or 401
- Called by App.jsx on load to check login state

**GET /auth/logout**
- Clears session, redirects to http://localhost:5173

### Drive Endpoint

**GET /drive/files?folder_link=...**
- Extracts folder ID from URL using regex (`/folders/<id>`)
- Fetches folder name from Drive API
- Lists files in folder (supports regular folders + Shared Drives via `supportsAllDrives=true`)
- Fetches all file contents in parallel via `fetch_all_contents`, writes to `_folder_cache`
- Triggers `index_files()` in a thread pool to build/rebuild the vector index for this folder
- `index_files` is wrapped in try/except — indexing failure never breaks file listing
- Returns `{ folder_name, files: [{id, name, mimeType}] }`

### Chat Endpoint

**POST /chat**
- Body: `{ folder_link, message, history: [{role, text}] }`
- **Primary path (RAG):** calls `search(email, folder_id, message, top_k=5)` — embeds the query, retrieves top-K relevant chunks from ChromaDB, builds context from those chunks with file name + page label header
- **Fallback path (context stuffing):** used when vector index is empty; reads from `_folder_cache` or re-fetches from Drive; also attempts `index_files` in background
- Sends context + history to Claude (`claude-haiku-4-5-20251001`) via Anthropic SDK
- **RAG citations:** `{name, id, passage, page_label}` — deduplicated by file, passage is the actual retrieved chunk, page_label is `"p. N"` / `"Slide N"` / null
- **Fallback citations:** `{name, id}` — name-match based (file name appears in answer text)

### Token Refresh

Access tokens expire after 1 hour. The backend handles this automatically:
- `auth_callback` saves `refresh_token` and `token_expiry` (unix timestamp) into the session
- `get_access_token(request, client)` — async helper called before any Drive API request:
  - If token is more than 60 seconds from expiry → return it as-is
  - If expired → POST to `https://oauth2.googleapis.com/token` with the refresh token
  - Updates `access_token` and `token_expiry` in the session, returns the fresh token
- Both `/drive/files` and `/chat` call `await get_access_token(request, client)` inside their `async with httpx.AsyncClient()` block

**One-time requirement:** the user must log out and back in once after this change so the session captures the `refresh_token`. Subsequent sessions are fully automatic.

### In-Memory Cache

File contents are cached after the first `/drive/files` call so the fallback path in `/chat` never re-downloads files.

- `_folder_cache: dict[tuple[str, str], FolderCache]` — keyed by `(email, folder_id)`
- `FolderCache` — dataclass holding `files: list[dict]` and `fetched_at: float`
- `CACHE_TTL = 600` — entries expire after 10 minutes
- Eager population: `/drive/files` calls `fetch_all_contents` (parallel via `asyncio.gather`) and writes to cache
- `/chat` fallback path checks cache first; on miss or expiry, re-fetches and updates cache

### RAG with Vector Search — COMPLETE

Implemented in `vectorstore.py`. Used as the primary retrieval path in `/chat`.

**Design decisions:**
- **Vector DB:** ChromaDB — local, no infrastructure, persists to `./chroma_db/` on disk
- **Embedding model:** Google `text-embedding-004` — reuses existing Google OAuth connection, only needs `GOOGLE_API_KEY` (no new service)
- **Chunk size:** 500 chars with 50-char overlap so context around boundaries is preserved
- **Page-aware chunking:** chunks are generated within section boundaries (per PDF page, per pptx slide), so every chunk has exact page attribution — no chunk ever spans two pages
- **Collection key:** `md5(email:folder_id)` — 32-char hex, valid ChromaDB collection name, unique per user+folder
- **Rebuild on re-index:** collection is deleted and recreated each time `index_files` is called, so stale chunks never accumulate

**`parsers.py` — `get_file_content` returns `(flat_text, sections)`:**
- `flat_text: str | None` — used for fallback context-stuffing path
- `sections: list[{text, page_label}]` — used by vectorstore for page-aware chunking
- PDFs: one section per page, `page_label = "p. N"`
- `.pptx`: one section per slide, `page_label = "Slide N"`
- All other types: single section, `page_label = None`

**`vectorstore.py` API:**
- `index_files(email, folder_id, file_contents)` — chunks all files within section boundaries, embeds in batches of 100, upserts into ChromaDB with `{file_id, file_name, page_label}` metadata
- `search(email, folder_id, query, top_k=5)` — embeds the query, returns top-K chunks as `[{file_id, file_name, page_label, passage}]`

**Flow:**
1. User submits folder → `/drive/files` fetches contents (with sections) → `index_files()` runs in thread pool
2. User sends message → `/chat` calls `search()` → top-5 chunks passed to Claude with page-labeled headers
3. Citations include `passage` (the actual chunk text), `page_label` (e.g. `"p. 3"`), and link to Drive file

### Known Limitations
- Image files are not readable (no OCR)
- File content is capped at 10k characters per file before chunking
- Cache is in-memory only — lost on server restart; vector index persists to disk
- ChromaDB collection rebuilds fully on every re-index (acceptable for small folders; inefficient for very large ones)
- No cross-user isolation beyond `(email, folder_id)` key
- Google Slides (.pptx export via Drive API) exported as plain text — no per-slide section labels (only native .pptx uploads get slide labels)

### Dependencies (requirements.txt)
- `fastapi`, `uvicorn[standard]`, `python-dotenv`, `httpx`, `itsdangerous` — core
- `anthropic` — Claude SDK
- `python-docx` — `.docx` parsing
- `pypdf` — PDF parsing
- `python-pptx` — `.pptx` parsing (text frames + tables, per-slide sections)
- `openpyxl` — `.xlsx` parsing (`data_only=True`)
- `chromadb` — local vector database
- `google-generativeai` — Google `text-embedding-004` embedding API
