import sqlite3
import os
from typing import List, Optional, Tuple
from contextlib import contextmanager

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "chat_viewer.db")


def get_db_path():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    return DATABASE_PATH


@contextmanager
def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                msg_id INTEGER NOT NULL,
                chat_id TEXT NOT NULL,
                user_id TEXT,
                user_name TEXT,
                text TEXT,
                date INTEGER NOT NULL,
                file_type TEXT DEFAULT 'text',
                file_data BLOB,
                file_name TEXT,
                thumb_data TEXT,
                thumb_w INTEGER DEFAULT 0,
                thumb_h INTEGER DEFAULT 0,
                is_channel_forward INTEGER DEFAULT 0,
                raw_json TEXT,
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_text ON messages(text)
        """)

        # Migration: add missing columns if not exists
        cursor.execute("PRAGMA table_info(messages)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'is_channel_forward' not in columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN is_channel_forward INTEGER DEFAULT 0")
        if 'user_name' not in columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN user_name TEXT")
        if 'thumb_data' not in columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN thumb_data TEXT")
        if 'thumb_w' not in columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN thumb_w INTEGER DEFAULT 0")
        if 'thumb_h' not in columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN thumb_h INTEGER DEFAULT 0")

        conn.commit()


def insert_chat(chat_id: str, name: str) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO chats (chat_id, name) VALUES (?, ?)",
            (chat_id, name)
        )
        conn.commit()
        return cursor.lastrowid


def insert_user(user_id: str, name: str) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, name) VALUES (?, ?)",
            (user_id, name)
        )
        conn.commit()
        return cursor.lastrowid


def insert_message(
    msg_id: int,
    chat_id: str,
    user_id: Optional[str],
    text: str,
    date: int,
    file_type: str,
    file_data: Optional[bytes],
    file_name: Optional[str],
    raw_json: str,
    user_name: Optional[str] = None,
    is_channel_forward: bool = False,
    thumb_data: Optional[str] = None,
    thumb_w: int = 0,
    thumb_h: int = 0
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO messages
               (msg_id, chat_id, user_id, user_name, text, date, file_type, file_data, file_name, is_channel_forward, raw_json, thumb_data, thumb_w, thumb_h)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, chat_id, user_id, user_name, text, date, file_type, file_data, file_name, int(is_channel_forward), raw_json, thumb_data, thumb_w, thumb_h)
        )
        conn.commit()
        return cursor.lastrowid


def insert_message_batch(messages: List[Tuple]) -> None:
    """Batch insert messages for performance. Tuple format:
    (msg_id, chat_id, user_id, user_name, text, date, file_type, file_data, file_name, is_channel_forward, raw_json, thumb_data, thumb_w, thumb_h)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """INSERT INTO messages
               (msg_id, chat_id, user_id, user_name, text, date, file_type, file_data, file_name, is_channel_forward, raw_json, thumb_data, thumb_w, thumb_h)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            messages
        )
        conn.commit()


def get_chats() -> List[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.chat_id, c.name, COUNT(m.id) as message_count
            FROM chats c
            LEFT JOIN messages m ON c.chat_id = m.chat_id
            GROUP BY c.chat_id, c.name
        """)
        return cursor.fetchall()


def get_chat_users(chat_id: str) -> List[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.user_id, u.name, COUNT(m.id) as message_count
            FROM messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE m.chat_id = ?
            GROUP BY u.user_id, u.name
            ORDER BY message_count DESC
        """, (chat_id,))
        return cursor.fetchall()


def get_messages(
    chat_id: str,
    page: int = 1,
    page_size: int = 50,
    user_id: Optional[str] = None,
    search: Optional[str] = None
) -> Tuple[List[Tuple], int]:
    with get_connection() as conn:
        cursor = conn.cursor()

        where_clauses = ["m.chat_id = ?"]
        params = [chat_id]

        if user_id:
            where_clauses.append("m.user_id = ?")
            params.append(user_id)

        if search:
            where_clauses.append("m.text LIKE ? COLLATE NOCASE")
            params.append(f"%{search}%")

        where_sql = " AND ".join(where_clauses)

        cursor.execute("SELECT COUNT(*) FROM messages m WHERE " + where_sql, params)
        total = cursor.fetchone()[0]

        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT m.id, m.msg_id, m.chat_id, m.user_id, m.user_name, m.text, m.date,
                   m.file_type, m.file_name, m.is_channel_forward, m.thumb_w, m.thumb_h, m.thumb_data
            FROM messages m
            WHERE {where_sql}
            ORDER BY m.date ASC
            LIMIT ? OFFSET ?
        """, params + [page_size, offset])

        return cursor.fetchall(), total


def get_message_detail(msg_id: int) -> Optional[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.id, m.msg_id, m.chat_id, m.user_id, m.user_name, m.text, m.date,
                   m.file_type, m.file_name, m.is_channel_forward, m.raw_json,
                   m.thumb_data, m.thumb_w, m.thumb_h
            FROM messages m
            WHERE m.id = ?
        """, (msg_id,))
        return cursor.fetchone()


def get_media_data(msg_id: int) -> Optional[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT file_data, file_type, file_name, thumb_data, thumb_w, thumb_h FROM messages WHERE id = ?",
            (msg_id,)
        )
        return cursor.fetchone()


def get_message_context(msg_id: int, count: int = 30) -> Tuple[List[Tuple], List[Tuple]]:
    print(f"get_message_context called with msg_id={msg_id}, count={count}")
    """Get context messages around a given message using database id ordering.
    Returns (before_messages, after_messages) tuples.
    Database id is auto-increment and corresponds to insertion order.
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get the target message's chat_id and msg_id
        cursor.execute(
            "SELECT id, chat_id, msg_id FROM messages WHERE id = ?",
            (msg_id,)
        )
        row = cursor.fetchone()
        if not row:
            return [], []

        target_db_id, chat_id, target_msg_id = row[0], row[1], row[2]

        # Get messages before (older messages in chronological order)
        # Lower msg_id = older message; we want the CLOSEST older, so DESC then reverse
        cursor.execute("""
            SELECT m.id, m.msg_id, m.chat_id, m.user_id, m.user_name, m.text, m.date,
                   m.file_type, m.file_name, m.is_channel_forward, m.thumb_w, m.thumb_h, m.thumb_data
            FROM messages m
            WHERE m.chat_id = ? AND m.msg_id < ?
            ORDER BY m.msg_id DESC
            LIMIT ?
        """, (chat_id, target_msg_id, count))
        before = list(reversed(cursor.fetchall()))

        # Get messages after (newer messages in chronological order)
        # Higher msg_id = newer message; ASC gives oldest first among newer messages
        cursor.execute("""
            SELECT m.id, m.msg_id, m.chat_id, m.user_id, m.user_name, m.text, m.date,
                   m.file_type, m.file_name, m.is_channel_forward, m.thumb_w, m.thumb_h, m.thumb_data
            FROM messages m
            WHERE m.chat_id = ? AND m.msg_id > ?
            ORDER BY m.msg_id ASC
            LIMIT ?
        """, (chat_id, target_msg_id, count))
        after = cursor.fetchall()

        return before, after


def delete_chat(chat_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        cursor.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        conn.commit()
