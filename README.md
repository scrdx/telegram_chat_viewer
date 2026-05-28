# Telegram Chat Viewer

Telegram 聊天记录查看器 - 将导出的 JSON 文件解析并以聊天界面展示。

## 快速开始

### 1. 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址: http://localhost:5173

## 功能

- 上传 JSON 文件解析 Telegram 聊天记录
- 聊天界面展示（气泡样式）
- 深色/浅色主题切换
- 搜索消息内容
- 按用户筛选
- 分页浏览
- 右键查看消息详情（包含原始 JSON）
- 图片/语音媒体预览
- 复制文本或 JSON

## 技术栈

- Frontend: React + TypeScript + Vite
- Backend: FastAPI + SQLite
- 支持检测 base64 编码的语音/图片
