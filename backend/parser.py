import json
import base64
import re
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class ParsedMessage:
    msg_id: int
    user_id: Optional[str]
    text: str
    date: int
    file_type: str
    file_data: Optional[bytes]
    file_name: Optional[str]
    raw_json: str


MAGIC_BYTES = {
    b'\x89PNG\r\n\x1a\n': 'image',
    b'\xff\xd8\xff': 'image',
    b'GIF87a': 'image',
    b'GIF89a': 'image',
    b'RIFF': 'audio',  # Could be WAV or WEBP
    b'fLaC': 'audio',
    b'ID3': 'audio',  # MP3
    b'OggS': 'audio',  # OGA
    b'\x00\x00\x01\x00': 'image',  # ICO
    b'\x00\x00\x02\x00': 'image',  # CUR
    b'BPG': 'image',
    b'Simple ': 'image',  # WebP
    b'\x12\x06': 'image',  # JXR
}


def detect_media_type(data: bytes) -> Optional[str]:
    if len(data) < 12:
        return None

    for magic, media_type in MAGIC_BYTES.items():
        if data[:len(magic)] == magic:
            return media_type

    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image'  # WEBP in RIFF container

    return None


def is_likely_base64(s: str) -> bool:
    if len(s) < 100:
        return False

    if not re.match(r'^[A-Za-z0-9+/]+=*$', s):
        return False

    try:
        decoded = base64.b64decode(s)
        media_type = detect_media_type(decoded)
        return media_type is not None
    except Exception:
        return False


def try_decode_base64(s: str) -> Tuple[Optional[str], Optional[bytes], Optional[str]]:
    if not is_likely_base64(s):
        return s, None, None

    try:
        decoded = base64.b64decode(s)
        media_type = detect_media_type(decoded)

        if media_type:
            extension = {
                'image': 'bin',
                'audio': 'bin',
                'video': 'bin'
            }.get(media_type, 'bin')

            if decoded[:4] == b'\x89PNG':
                extension = 'png'
            elif decoded[:3] == b'\xff\xd8\xff':
                extension = 'jpg'
            elif decoded[:4] == b'BPG':
                extension = 'bpg'

            return None, decoded, f"decoded_media.{extension}"

        return s, None, None
    except Exception:
        return s, None, None


def parse_message(raw_msg: Dict[str, Any]) -> ParsedMessage:
    msg_id = raw_msg.get('id', 0)

    raw = raw_msg.get('raw', {})
    from_id = raw.get('FromID', {})
    user_id = from_id.get('UserID') if isinstance(from_id, dict) else None

    if not user_id:
        peer_id = raw.get('PeerID', {})
        if isinstance(peer_id, dict):
            if 'UserID' in peer_id:
                user_id = peer_id.get('UserID')
            elif 'ChannelID' in peer_id:
                user_id = f"channel_{peer_id.get('ChannelID')}"

    text = raw_msg.get('text', '')
    date = raw_msg.get('date', 0)

    file_name = raw_msg.get('file', '')
    file_type = 'text'
    file_data = None

    if file_name:
        ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'):
            file_type = 'image'
        elif ext in ('mp3', 'ogg', 'oga', 'wav', 'm4a'):
            file_type = 'voice'
        elif ext in ('mp4', 'mov', 'avi', 'mkv', 'webm'):
            file_type = 'video'
        elif ext in ('webm', 'tgs'):
            file_type = 'sticker'

    media = raw.get('Media')
    if media and isinstance(media, dict):
        photo = media.get('Photo')
        if photo:
            file_type = 'image'

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

    if not file_data and file_name and '.' in file_name:
        pass

    return ParsedMessage(
        msg_id=msg_id,
        user_id=str(user_id) if user_id else None,
        text=text or '',
        date=date,
        file_type=file_type,
        file_data=file_data,
        file_name=file_name,
        raw_json=json.dumps(raw_msg, ensure_ascii=False)
    )


def parse_json_file(file_path: str) -> Tuple[str, List[ParsedMessage], Dict[str, str]]:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    chat_id = str(data.get('id', ''))
    messages = data.get('messages', [])

    users = {}
    parsed_messages = []

    for msg in messages:
        parsed = parse_message(msg)
        parsed_messages.append(parsed)

        if parsed.user_id and parsed.text:
            if parsed.user_id not in users:
                users[parsed.user_id] = parsed.text[:50]
            else:
                if len(parsed.text) > len(users[parsed.user_id]):
                    users[parsed.user_id] = parsed.text[:50]

    for user_id, name in users.items():
        if not name or name.strip() == '':
            users[user_id] = f"User_{user_id[:8]}"

    return chat_id, parsed_messages, users
