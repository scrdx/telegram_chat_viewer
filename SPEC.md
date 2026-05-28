# Telegram Chat Viewer - Specification

## Overview

A web application for viewing Telegram chat exports in a chat-like interface with search, user filtering, and message details inspection.

## Tech Stack

- **Frontend**: React + TypeScript + Vite
- **Backend**: FastAPI + Python
- **Database**: SQLite
- **Styling**: CSS with dark/light theme support

## Project Structure

```
telegram_chat_viewer/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── models.py            # Pydantic models
│   ├── database.py          # SQLite operations
│   ├── parser.py            # JSON parsing + base64 detection
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main React component
│   │   ├── main.tsx
│   │   ├── index.css
│   │   └── types/index.ts
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── data/                    # SQLite DB stored here
├── SPEC.md
└── README.md
```

## Features

- [x] Upload and parse Telegram JSON export
- [x] Display messages in chat bubble UI
- [x] Dark/light theme toggle
- [x] Search messages by text
- [x] Filter by user
- [x] Pagination
- [x] Right-click context menu for message details
- [x] View raw JSON of any message
- [x] Image/voice media preview
- [x] Copy text/JSON to clipboard
- [x] SQLite storage for fast searching
- [x] Base64-encoded media detection
- [x] Multi-group support with sidebar navigation

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/parse` | Upload JSON file to parse |
| GET | `/api/chats` | List all parsed chats |
| GET | `/api/chats/{chat_id}/messages` | Get messages (paginated, filterable) |
| GET | `/api/chats/{chat_id}/users` | Get users in a chat |
| GET | `/api/messages/{msg_id}` | Get message details with raw JSON |
| GET | `/api/media/{msg_id}` | Get media binary data |

## Running the Application

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173` and proxies API requests to `http://localhost:8000`.

## Database Schema

### chats
- `chat_id` (TEXT, PK)
- `name` (TEXT)

### users
- `user_id` (TEXT, PK)
- `name` (TEXT)

### messages
- `id` (INTEGER, PK)
- `msg_id` (INTEGER)
- `chat_id` (TEXT, FK)
- `user_id` (TEXT, FK)
- `text` (TEXT)
- `date` (INTEGER, timestamp)
- `file_type` (TEXT: text/image/voice/video/sticker)
- `file_data` (BLOB, decoded media)
- `file_name` (TEXT)
- `raw_json` (TEXT)

Indexes on: `chat_id`, `user_id`, `date`, `text`
