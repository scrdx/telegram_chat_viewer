from pydantic import BaseModel
from typing import Optional, List, Any


class ChatInfo(BaseModel):
    chat_id: str
    name: str
    message_count: int = 0
    user_count: int = 0


class UserInfo(BaseModel):
    user_id: str
    name: str
    message_count: int = 0


class MessageBase(BaseModel):
    id: int
    msg_id: int
    chat_id: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    text: str
    date: int
    file_type: str
    file_name: Optional[str] = None
    is_channel_forward: bool = False


class MessageDetail(MessageBase):
    raw_json: str


class ParseResult(BaseModel):
    chat_name: str
    message_count: int
    user_count: int


class PageResponse(BaseModel):
    messages: List[MessageBase]
    total: int
    page: int
    page_size: int
    total_pages: int
