export interface ChatInfo {
  chat_id: string;
  name: string;
  message_count: number;
  user_count?: number;
}

export interface UserInfo {
  user_id: string;
  name: string;
  message_count: number;
}

export interface MessageBase {
  id: number;
  msg_id: number;
  chat_id: string;
  user_id: string | null;
  user_name: string | null;
  text: string;
  date: number;
  file_type: string;
  file_name: string | null;
  is_channel_forward: boolean;
  thumb_w?: number;
  thumb_h?: number;
  thumb_data?: string;
}

export interface MessageDetail extends MessageBase {
  raw_json: string;
}

export interface PageResponse {
  messages: MessageBase[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ParseResult {
  chat_name: string;
  message_count: number;
  user_count: number;
}
