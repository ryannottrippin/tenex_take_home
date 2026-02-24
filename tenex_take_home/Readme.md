# Google Drive AI Chat

A web app that lets you sign in with Google, point it at a Drive folder, and have an AI-powered conversation about the files inside — with citations back to the source pages.

---

## Prerequisites

- **Python** (via [conda](https://docs.conda.io/en/latest/miniconda.html))
- **Node.js** (v18+) and **npm**
- A **Google Cloud** project with OAuth 2.0 credentials
- An **Anthropic API key** (for Claude)
- A **Google AI Studio API key** (for embeddings)

---

## 1. Google Cloud Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or use an existing one).
3. Enable these APIs:
   - **Google Drive API**
   - **Google People API** (for user profile info)
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**.
   - Application type: **Web application**
   - Authorized redirect URI: `http://localhost:8000/auth/callback`
5. Copy your **Client ID** and **Client Secret**.

---

## 2. Backend Setup

### Create and activate a conda environment

```bash
conda create -n drive-chat python=3.11
conda activate drive-chat
```

### Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Create the `.env` file

Create a file at `backend/.env` with the following contents:

```env
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
SESSION_SECRET=any-random-string-you-choose
ANTHROPIC_API_KEY=your-anthropic-api-key
GOOGLE_API_KEY=your-google-ai-studio-api-key
```

- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — from step 1 above
- `SESSION_SECRET` — any long random string (used to sign session cookies)
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com/)
- `GOOGLE_API_KEY` — from [aistudio.google.com](https://aistudio.google.com/) (used for text embeddings)

### Start the backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The backend runs on **http://localhost:8000**.

---

## 3. Frontend Setup

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on **http://localhost:5173**.

---

## 4. Using the App

1. Open **http://localhost:5173** in your browser.
2. Click **Continue with Google** and sign in.
3. Copy a Google Drive folder URL (e.g. `https://drive.google.com/drive/folders/abc123`) and paste it in.
4. The app will index the files in the folder — this may take a few seconds.
5. Start chatting. Responses include citations that link back to the source files, with page or slide numbers where applicable.

> **Note:** The first time you log in after setting up the backend, make sure to complete the full OAuth flow so the app can capture your refresh token. If your session ever stops working, log out and back in.

---

## Running the Tests

The test suite covers all API routes, request schemas, and service helpers. All external calls (Google APIs, Anthropic, ChromaDB) are mocked — no network connection or real credentials required.

### Install pytest

```bash
conda activate drive-chat
pip install pytest
```

### Run

```bash
# From the project root (same folder as pytest.ini)
pytest
```

To see individual test names as they run:

```bash
pytest -v
```

### What is tested

| File | Covers |
|------|--------|
| `tests/test_health.py` | `GET /health` |
| `tests/test_auth.py` | `/auth/me`, `/auth/google`, `/auth/callback`, `/auth/logout` |
| `tests/test_drive.py` | `GET /drive/files` — auth guard, validation, Drive API errors, happy path |
| `tests/test_chat.py` | `POST /chat` — RAG path, fallback cache, Claude 529 → 503 |
| `tests/test_exceptions.py` | `AppException` error format contract |
| `tests/test_schemas.py` | `ChatRequest` + `HistoryMessage` Pydantic validation |
| `tests/test_services.py` | `extract_folder_id()` URL parsing |

---

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app factory — middleware + router registration
│   ├── core/
│   │   ├── config.py        # pydantic-settings — typed config from .env
│   │   ├── exceptions.py    # AppException + global error handler
│   │   └── dependencies.py  # get_current_user auth guard
│   ├── routers/
│   │   ├── auth.py          # /auth/* routes
│   │   ├── drive.py         # /drive/* routes
│   │   └── chat.py          # /chat route
│   ├── schemas/
│   │   └── chat.py          # ChatRequest + HistoryMessage Pydantic models
│   ├── services/
│   │   └── drive.py         # Shared cache + Drive API helpers
│   ├── parsers.py           # File content extraction (PDF, PPTX, DOCX, etc.)
│   ├── vectorstore.py       # ChromaDB indexing and semantic search
│   ├── requirements.txt
│   └── .env                 # Secrets — you create this (not committed)
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # Screen router
│   │   ├── main.jsx          # React entry point
│   │   ├── index.css         # All styles
│   │   ├── api/
│   │   │   ├── client.js     # Base fetch wrapper
│   │   │   ├── auth.js       # getMe(), LOGIN_URL
│   │   │   ├── drive.js      # getFiles()
│   │   │   └── chat.js       # sendMessage()
│   │   └── components/
│   │       ├── AuthScreen.jsx
│   │       ├── DriveInput.jsx
│   │       └── ChatInterface.jsx
│   ├── package.json
│   └── vite.config.js
└── tests/
    ├── conftest.py           # Shared fixtures
    ├── test_health.py
    ├── test_auth.py
    ├── test_drive.py
    ├── test_chat.py
    ├── test_exceptions.py
    ├── test_schemas.py
    └── test_services.py
```

---

## Supported File Types

| Type | Extension |
|------|-----------|
| PDF | `.pdf` — page-level citations |
| PowerPoint | `.pptx` — slide-level citations |
| Word | `.docx` |
| Excel | `.xlsx` |
| Plain text / Markdown | `.txt`, `.md` |
| Google Docs / Sheets / Slides | exported automatically via Drive API |

> Images are not supported (no OCR). File content is capped at 10,000 characters per file.

---

## Troubleshooting

**"Sign in with Google" redirects to an error**
- Check that your OAuth redirect URI is exactly `http://localhost:8000/auth/callback` in Google Cloud Console.
- Make sure `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env` are correct.

**No files appear in the sidebar**
- Confirm the Drive folder is accessible to the account you signed in with.
- Shared Drive folders are supported — make sure you're using the full folder URL.

**Chat responses have no citations or seem unaware of file content**
- The vector index builds in the background after you submit a folder. Wait a few seconds and try again.
- Check the backend terminal for any indexing errors.

**Token expired / can't access Drive after a while**
- Log out (top-right menu) and sign back in. The app will capture a fresh refresh token and handle renewals automatically going forward.
