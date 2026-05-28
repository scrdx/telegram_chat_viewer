import os
import math
import json
import queue
import threading
import uuid
import time
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from typing import Optional

from models import ChatInfo, UserInfo, MessageBase, MessageDetail, PageResponse
from database import init_database, insert_chat, insert_user, insert_message_batch
from database import get_chats, get_chat_users, get_messages, get_message_detail, get_media_data, get_message_context

app = FastAPI(title="Telegram Chat Viewer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store import tasks in memory
import_tasks = {}


@app.on_event("startup")
def startup():
    init_database()


@app.post("/api/parse")
async def start_import(file: UploadFile = File(...)):
    """Step 1: Save file to data directory and return immediately with task_id."""
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Only JSON files are supported")

    upload_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(upload_dir, exist_ok=True)

    # Generate unique task ID
    task_id = str(uuid.uuid4())

    # Save file synchronously
    file_path = os.path.join(upload_dir, f"upload_{task_id}.json")
    try:
        contents = await file.read()
        with open(file_path, 'wb') as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Initialize task status
    import_tasks[task_id] = {
        'status': 'pending',
        'step': 'Waiting to start...',
        'progress': 0,
        'current': 0,
        'total': 0,
        'error': None,
        'result': None,
        'file_path': file_path
    }

    # Start background import thread
    thread = threading.Thread(target=_run_import, args=(task_id,))
    thread.daemon = True
    thread.start()

    return JSONResponse({
        'task_id': task_id,
        'status': 'started',
        'message': 'Import started'
    })


def _run_import(task_id: str):
    """Background thread to run the import."""
    task = import_tasks[task_id]
    file_path = task['file_path']

    # Ensure database is initialized
    init_database()

    try:
        task['status'] = 'parsing'
        task['step'] = 'Reading JSON file...'

        # Read and parse JSON
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        chat_id = str(data.get('id', ''))
        chat_name = os.path.basename(file_path).replace('.json', '').replace('upload_', '')
        messages = data.get('messages', [])
        total = len(messages)

        if total == 0:
            task['status'] = 'error'
            task['error'] = 'No messages found in file'
            return

        task['total'] = total
        task['step'] = f'Parsing {total} messages...'

        # Parse messages
        parsed_messages = []
        users = {}

        for i, raw_msg in enumerate(messages):
            parsed = _parse_message(raw_msg, chat_id)
            parsed_messages.append(parsed)

            if parsed.user_id:
                uid = parsed.user_id
                # Use user_name if available, otherwise use user_id as name
                if uid not in users:
                    users[uid] = parsed.user_name or f"User_{uid[:8]}" if len(uid) >= 8 else f"User_{uid}"

            if (i + 1) % 1000 == 0 or i == total - 1:
                task['current'] = i + 1
                task['progress'] = int((i + 1) / total * 50)
                task['step'] = f'Parsing: {i + 1}/{total}'

        task['step'] = f'Saving {len(parsed_messages)} messages...'

        # Save to database
        insert_chat(chat_id, chat_name)

        for uid, name in users.items():
            insert_user(uid, name)

        # Batch insert
        batch_size = 1000
        saved = 0
        for i in range(0, len(parsed_messages), batch_size):
            batch = parsed_messages[i:i + batch_size]
            msg_batch = [
                (
                    p.msg_id, p.chat_id, p.user_id, p.user_name, p.text,
                    p.date, p.file_type, p.file_data, p.file_name,
                    int(p.is_channel_forward), p.raw_json,
                    getattr(p, 'thumb_data', None),
                    getattr(p, 'thumb_w', 0),
                    getattr(p, 'thumb_h', 0)
                )
                for p in batch
            ]
            insert_message_batch(msg_batch)
            saved += len(batch)
            task['current'] = saved
            task['progress'] = 50 + int(saved / len(parsed_messages) * 50)
            task['step'] = f'Saving: {saved}/{len(parsed_messages)}'

        # Cleanup temp file
        try:
            os.remove(file_path)
        except:
            pass

        task['status'] = 'complete'
        task['progress'] = 100
        task['step'] = 'Import complete!'
        task['result'] = {
            'chat_name': chat_name,
            'message_count': len(parsed_messages),
            'user_count': len(users)
        }

    except json.JSONDecodeError as e:
        task['status'] = 'error'
        task['error'] = f'Invalid JSON: {str(e)}'
    except Exception as e:
        task['status'] = 'error'
        task['error'] = f'Error: {str(e)}'


@app.get("/api/parse/{task_id}")
def get_import_status(task_id: str):
    """Step 2: Get import progress."""
    if task_id not in import_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = import_tasks[task_id]
    return JSONResponse({
        'status': task['status'],
        'step': task['step'],
        'progress': task['progress'],
        'current': task['current'],
        'total': task['total'],
        'error': task['error'],
        'result': task['result']
    })


def _parse_message(raw_msg: dict, chat_id: str):
    """Parse a single message from Telegram JSON export."""
    import base64
    import re

    MAGIC_BYTES = {
        b'\x89PNG\r\n\x1a\n': 'image',
        b'\xff\xd8\xff': 'image',
        b'GIF87a': 'image',
        b'GIF89a': 'image',
        b'fLaC': 'audio',
        b'ID3': 'audio',
        b'OggS': 'audio',
    }

    def detect_media_type(data: bytes) -> Optional[str]:
        if len(data) < 12:
            return None
        for magic, media_type in MAGIC_BYTES.items():
            if data[:len(magic)] == magic:
                return media_type
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return 'image'
        return None

    def is_likely_base64_media(s: str) -> bool:
        if len(s) < 100:
            return False
        if not re.match(r'^[A-Za-z0-9+/]+=*$', s):
            return False
        try:
            decoded = base64.b64decode(s)
            return detect_media_type(decoded) is not None
        except:
            return False

    def try_decode_base64(s):
        if not is_likely_base64_media(s):
            return s, None, None
        try:
            decoded = base64.b64decode(s)
            media_type = detect_media_type(decoded)
            if media_type:
                ext = 'png' if decoded[:4] == b'\x89PNG' else 'jpg' if decoded[:3] == b'\xff\xd8\xff' else 'bin'
                return None, decoded, f"decoded_media.{ext}"
            return s, None, None
        except:
            return s, None, None

    msg_id = raw_msg.get('id', 0)
    date = raw_msg.get('date', 0)
    text = raw_msg.get('text', '')
    file_name = raw_msg.get('file', '')

    raw = raw_msg.get('raw', {})

    user_id = None
    user_name = None
    is_channel_forward = False

    from_id = raw.get('FromID', {})
    if isinstance(from_id, dict):
        if 'UserID' in from_id:
            user_id = str(from_id['UserID'])
        elif 'ChannelID' in from_id:
            user_id = str(from_id['ChannelID'])
            is_channel_forward = True

    if not user_id:
        peer_id = raw.get('PeerID', {})
        if isinstance(peer_id, dict):
            if 'UserID' in peer_id:
                user_id = str(peer_id['UserID'])
            elif 'ChannelID' in peer_id:
                user_id = str(peer_id['ChannelID'])

    if not user_name:
        if isinstance(from_id, dict):
            fn = from_id.get('FirstName', '')
            ln = from_id.get('LastName', '')
            if fn or ln:
                user_name = f"{fn} {ln}".strip()

    if not user_name:
        fn = raw.get('FirstName', '')
        ln = raw.get('LastName', '')
        if fn or ln:
            user_name = f"{fn} {ln}".strip()

    file_type = 'text'
    file_data = None
    thumb_data = None
    thumb_w = 0
    thumb_h = 0

    if file_name:
        ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'):
            file_type = 'image'
        elif ext in ('mp3', 'ogg', 'oga', 'wav', 'm4a', 'opus'):
            file_type = 'voice'
        elif ext in ('mp4', 'mov', 'avi', 'mkv', 'webm'):
            file_type = 'video'
        elif ext in ('webm', 'tgs'):
            file_type = 'sticker'

    # Check raw.Document for embedded files (stickers, files, etc.)
    doc = raw.get('Document', {})
    if isinstance(doc, dict):
        doc_type = doc.get('Type', '')
        doc_attrs = doc.get('Attributes', [])
        doc_mime = doc.get('MimeType', '')

        # Check if it's a sticker
        for attr in doc_attrs:
            if isinstance(attr, dict) and attr.get('Type') == 'DocumentAttributeSticker':
                file_type = 'sticker'
                break

        # Get file bytes from Document
        doc_bytes = doc.get('Bytes', b'')
        if doc_bytes:
            if isinstance(doc_bytes, str):
                # Base64 encoded string - decode it
                try:
                    file_data = base64.b64decode(doc_bytes)
                except:
                    file_data = None
            else:
                file_data = doc_bytes
            if not file_name:
                file_name = doc.get('FileName', '') or f"document.{doc_mime.split('/')[-1] if doc_mime else 'bin'}"

        # Determine file type from mime
        if doc_mime:
            if 'image' in doc_mime:
                file_type = 'image'
            elif 'audio' in doc_mime or 'voice' in doc_mime:
                file_type = 'voice'
            elif 'video' in doc_mime:
                file_type = 'video'

        # Extract thumbnail from Thumbs (keep as base64 string for frontend display)
        thumbs = doc.get('Thumbs', [])
        if isinstance(thumbs, list) and len(thumbs) > 0:
            thumb = thumbs[0]
            if isinstance(thumb, dict):
                thumb_bytes = thumb.get('Bytes', '')
                if thumb_bytes and isinstance(thumb_bytes, str):
                    # Keep as base64 string for frontend data URL
                    thumb_data = thumb_bytes
                    thumb_w = thumb.get('W', 0)
                    thumb_h = thumb.get('H', 0)

    media = raw.get('Media', {})
    if isinstance(media, dict) and media.get('Photo'):
        file_type = 'image'

    # If text is empty but we have a file, use file name as text representation
    if not text and file_name and file_type != 'text':
        text = f"[{file_type}: {file_name}]"

    if text and isinstance(text, str):
        text, decoded_data, decoded_name = try_decode_base64(text)
        if decoded_data:
            detected = detect_media_type(decoded_data)
            if detected == 'image':
                file_type = 'image'
            elif detected == 'audio':
                file_type = 'voice'
            file_data = decoded_data
            if decoded_name:
                file_name = decoded_name

    class ParsedMsg:
        pass

    m = ParsedMsg()
    m.msg_id = msg_id
    m.chat_id = chat_id
    m.user_id = user_id
    m.user_name = user_name
    m.text = text or ''
    m.date = date
    m.file_type = file_type
    m.file_data = file_data
    m.file_name = file_name
    m.thumb_data = thumb_data
    m.thumb_w = thumb_w
    m.thumb_h = thumb_h
    m.raw_json = json.dumps(raw_msg, ensure_ascii=False)
    m.is_channel_forward = is_channel_forward

    return m


@app.get("/api/chats", response_model=list[ChatInfo])
def list_chats():
    rows = get_chats()
    return [
        ChatInfo(
            chat_id=row[0],
            name=row[1],
            message_count=row[2] or 0
        )
        for row in rows
    ]


@app.get("/api/chats/{chat_id}/messages", response_model=PageResponse)
def list_messages(
    chat_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: Optional[str] = None,
    search: Optional[str] = None
):
    rows, total = get_messages(chat_id, page, page_size, user_id, search)

    messages = [
        MessageBase(
            id=row[0],
            msg_id=row[1],
            chat_id=row[2],
            user_id=row[3],
            user_name=row[4],
            text=row[5] or '',
            date=row[6],
            file_type=row[7] or 'text',
            file_name=row[8],
            is_channel_forward=bool(row[9]),
            thumb_w=row[10] if len(row) > 10 else 0,
            thumb_h=row[11] if len(row) > 11 else 0,
            thumb_data=row[12] if len(row) > 12 else None
        )
        for row in rows
    ]

    return PageResponse(
        messages=messages,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0
    )


@app.get("/api/chats/{chat_id}/users", response_model=list[UserInfo])
def list_chat_users(chat_id: str):
    rows = get_chat_users(chat_id)
    return [
        UserInfo(
            user_id=row[0],
            name=row[1] or f"User_{row[0][:8]}",
            message_count=row[2]
        )
        for row in rows
    ]


@app.get("/api/messages/{msg_id}", response_model=MessageDetail)
def get_message(msg_id: int):
    row = get_message_detail(msg_id)
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")

    return MessageDetail(
        id=row[0],
        msg_id=row[1],
        chat_id=row[2],
        user_id=row[3],
        user_name=row[4],
        text=row[5] or '',
        date=row[6],
        file_type=row[7] or 'text',
        file_name=row[8],
        is_channel_forward=bool(row[9]),
        raw_json=row[10]
    )


@app.get("/api/messages/{msg_id}/context")
def get_context(msg_id: int, count: int = Query(30, ge=1, le=100)):
    """Get messages around a given message for context view."""
    print(f"get_context called with msg_id={msg_id}, count={count}")
    before, after = get_message_context(msg_id, count)
    print(f"get_context returning: before={len(before)}, after={len(after)}")

    def row_to_message(row) -> MessageBase:
        return MessageBase(
            id=row[0],
            msg_id=row[1],
            chat_id=row[2],
            user_id=row[3],
            user_name=row[4],
            text=row[5] or '',
            date=row[6],
            file_type=row[7] or 'text',
            file_name=row[8],
            is_channel_forward=bool(row[9]),
            thumb_w=row[10] if len(row) > 10 else 0,
            thumb_h=row[11] if len(row) > 11 else 0,
            thumb_data=row[12] if len(row) > 12 else None
        )

    return {
        'before': [row_to_message(r) for r in before],
        'target': msg_id,
        'after': [row_to_message(r) for r in after]
    }


@app.get("/api/media/{msg_id}")
def get_media(msg_id: int, thumb: bool = False):
    row = get_media_data(msg_id)
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")

    file_data, file_type, file_name, thumb_data, thumb_w, thumb_h = row

    if thumb and thumb_data:
        import base64
        thumb_bytes = base64.b64decode(thumb_data)
        return Response(
            content=thumb_bytes,
            media_type="image/jpeg",
            headers={"Content-Disposition": f"inline; filename=thumb_{file_name or 'thumb'}"}
        )

    if not file_data:
        raise HTTPException(status_code=404, detail="Media not found")

    media_types = {
        'image': 'image/jpeg',
        'voice': 'audio/mpeg',
        'video': 'video/mp4',
        'sticker': 'image/webm',
    }

    content_type = media_types.get(file_type, 'application/octet-stream')

    return Response(
        content=file_data,
        media_type=content_type,
        headers={"Content-Disposition": f"inline; filename={file_name or 'media'}"}
    )


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str):
    from database import delete_chat as db_delete_chat
    db_delete_chat(chat_id)
    return {"status": "ok"}


@app.delete("/api/chats")
def delete_all_chats():
    from database import get_connection
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages")
        cursor.execute("DELETE FROM chats")
        cursor.execute("DELETE FROM users")
        conn.commit()
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
