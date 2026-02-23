# DriveChat

A web app that lets you have an AI-powered conversation about the files in any Google Drive folder. Sign in with Google, paste a folder link, and ask questions — the AI reads your documents and answers with citations linking back to the source files.

---

## What It Does

1. **Sign in with Google** — OAuth 2.0, read-only Drive access
2. **Paste a Google Drive folder link** — any folder you have access to
3. **Chat about the files** — AI reads all readable documents and answers questions
4. **Citations** — responses include clickable links to the source files, plus the exact passage retrieved

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite (port 5173) |
| Backend | FastAPI + Uvicorn (port 8000) |
| Auth | Google OAuth 2.0 |
| AI | Anthropic Claude (`claude-haiku-4-5-20251001`) |
| Embeddings | Google `text-embedding-004` |
| Vector DB | ChromaDB (local, persists to disk) |

---

## Architecture

### Retrieval: RAG over Google Drive

When you submit a folder, the backend:
1. Fetches all readable file contents from the Drive API in parallel
2. Chunks each file into ~500-character segments with 50-char overlap
3. Embeds each chunk using Google's `text-embedding-004` model
4. Stores the embeddings in a local ChromaDB collection keyed by `(user, folder)`

On each chat message:
1. The query is embedded using the same model
2. The top-5 most semantically similar chunks are retrieved
3. Only those chunks are sent to Claude as context (not the full folder)
4. Citations are derived from the retrieved chunk metadata — not guessed from the answer text

This means the app handles large folders without hitting context limits, and citations are precise.

### Fallback
If the vector index isn't ready (e.g. Google API key not configured, server restarted before re-indexing), the app falls back to context stuffing — all file contents are sent to Claude directly. Citations fall back to name-matching.

### Auth and Token Refresh
Google OAuth tokens expire after 1 hour. The backend automatically refreshes them using the stored `refresh_token` before any Drive API call.

---

## File Structure

```
tenex_take_home/
├── Readme.md
├── .gitignore
│
├── backend/
│   ├── main.py          # FastAPI app — auth, drive, and chat endpoints
│   ├── parsers.py       # File content extraction for all supported MIME types
│   ├── vectorstore.py   # ChromaDB + Google embeddings — indexing and search
│   ├── requirements.txt
│   ├── .env             # Secrets (not committed)
│   └── chroma_db/       # Persisted vector index (not committed)
│
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx           # Screen router (loading → auth → drive → chat)
        ├── index.css         # All styles
        └── components/
            ├── AuthScreen.jsx    # Sign in with Google
            ├── DriveInput.jsx    # Paste a folder link
            └── ChatInterface.jsx # Chat UI with sidebar, messages, citations
```

---

## Supported File Types

| Type | How it's read |
|---|---|
| Google Docs | Exported as plain text via Drive API |
| Google Sheets | Exported as CSV via Drive API |
| Google Slides | Exported as plain text via Drive API |
| `.docx` | Parsed with `python-docx` |
| `.pptx` | Parsed with `python-pptx` (text frames + tables) |
| `.xlsx` | Parsed with `openpyxl` (`data_only=True`) |
| `.pdf` | Parsed with `pypdf` |
| `.txt`, `.md`, `.csv`, `.json` | Downloaded directly |
| Images, binaries | Skipped |

---

## Setup

### Prerequisites
- Python (conda recommended)
- Node.js + npm
- A Google Cloud project with OAuth credentials
- An Anthropic API key
- A Google AI Studio API key (free)

### 1. Google Cloud — OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Web application)
3. Add `http://localhost:8000/auth/callback` as an Authorized Redirect URI
4. Enable the **Google Drive API** for your project
5. Copy the Client ID and Client Secret

### 2. Google AI Studio — Embedding API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create an API key
3. This is used for `text-embedding-004` (chunking and vector search)

### 3. Anthropic API Key

Get your key from [console.anthropic.com](https://console.anthropic.com).

### 4. Backend `.env`

Create `backend/.env`:

```env
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
SESSION_SECRET=any-random-string
ANTHROPIC_API_KEY=your-anthropic-key
GOOGLE_API_KEY=your-google-ai-studio-key
```

### 5. Install and Run

**Backend:**
```bash
conda activate your-env
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Then open [http://localhost:5173](http://localhost:5173).

---

## Known Limitations

- Images are not readable (no OCR)
- File content is capped at 10,000 characters per file before chunking
- The vector index persists to disk but is rebuilt when you re-submit a folder
- In-memory file cache is lost on server restart (vector index is not)
