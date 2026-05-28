import { useState, useEffect, useRef } from 'react'
import type { ChatInfo, UserInfo, MessageBase, MessageDetail, PageResponse } from './types'

const API_BASE = '/api'

function formatTime(timestamp: number): string {
  const date = new Date(timestamp * 1000)
  return date.toLocaleString()
}

function formatDate(timestamp: number): string {
  const date = new Date(timestamp * 1000)
  return date.toLocaleDateString()
}

export default function App() {
  const [theme, setTheme] = useState<'light' | 'dark'>('light')
  const [chats, setChats] = useState<ChatInfo[]>([])
  const [currentChat, setCurrentChat] = useState<ChatInfo | null>(null)
  const [users, setUsers] = useState<UserInfo[]>([])
  const [messages, setMessages] = useState<MessageBase[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [totalPages, setTotalPages] = useState(0)
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [selectedUser, setSelectedUser] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; message: MessageBase } | null>(null)
  const [selectedMessage, setSelectedMessage] = useState<MessageDetail | null>(null)
  const [mediaPreview, setMediaPreview] = useState<{ type: string; src: string } | null>(null)
  const [contextModal, setContextModal] = useState<{
    show: boolean
    targetMsg: MessageBase | null
    before: MessageBase[]
    after: MessageBase[]
    loading: boolean
    count: number
  }>({ show: false, targetMsg: null, before: [], after: [], loading: false, count: 50 })
  const [showJsonModal, setShowJsonModal] = useState(false)
  const [jsonContent, setJsonContent] = useState('')
  const [importModal, setImportModal] = useState<{
    show: boolean
    status: 'uploading' | 'processing' | 'complete' | 'error'
    step: string
    progress: number
    current?: number
    total?: number
    error?: string
    result?: { chat_name: string; message_count: number; user_count: number }
  }>({ show: false, status: 'uploading', step: '', progress: 0 })
  const fileInputRef = useRef<HTMLInputElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    loadChats()
  }, [])

  useEffect(() => {
    if (currentChat) {
      loadMessages(1)
      loadUsers()
    }
  }, [currentChat])

  useEffect(() => {
    if (currentChat) {
      loadMessages(1)
    }
  }, [search, selectedUser])

  useEffect(() => {
    const handleClick = () => setContextMenu(null)
    document.addEventListener('click', handleClick)
    return () => document.removeEventListener('click', handleClick)
  }, [])

  // Keyboard navigation for pagination
  useEffect(() => {
    if (!currentChat || totalPages <= 1) return
    const handleKeyDown = (e: KeyboardEvent) => {
      // Only handle when not typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'ArrowLeft' && page > 1) {
        loadMessages(page - 1)
      } else if (e.key === 'ArrowRight' && page < totalPages) {
        loadMessages(page + 1)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [currentChat, page, totalPages])

  async function loadChats() {
    try {
      const res = await fetch(`${API_BASE}/chats`)
      if (res.ok) {
        const data = await res.json()
        setChats(data)
        if (data.length > 0 && !currentChat) {
          setCurrentChat(data[0])
        }
      }
    } catch (e) {
      console.error('Failed to load chats:', e)
    }
  }

  async function loadUsers() {
    if (!currentChat) return
    try {
      const res = await fetch(`${API_BASE}/chats/${currentChat.chat_id}/users`)
      if (res.ok) {
        const data = await res.json()
        setUsers(data)
      }
    } catch (e) {
      console.error('Failed to load users:', e)
    }
  }

  async function loadMessages(newPage: number, overrideUser?: string, overridePageSize?: number) {
    if (!currentChat) return
    setLoading(true)
    const effectiveUser = overrideUser !== undefined ? overrideUser : selectedUser
    const effectivePageSize = overridePageSize !== undefined ? overridePageSize : pageSize
    try {
      const params = new URLSearchParams({
        page: String(newPage),
        page_size: String(effectivePageSize),
      })
      if (search) params.set('search', search)
      if (effectiveUser) params.set('user_id', effectiveUser)

      const res = await fetch(`${API_BASE}/chats/${currentChat.chat_id}/messages?${params}`)
      if (res.ok) {
        const data: PageResponse = await res.json()
        setMessages(data.messages)
        setPage(data.page)
        setTotalPages(data.total_pages)
        setTotal(data.total)
      }
    } catch (e) {
      console.error('Failed to load messages:', e)
    } finally {
      setLoading(false)
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    setImportModal({
      show: true,
      status: 'uploading',
      step: 'Uploading file...',
      progress: 0
    })

    const formData = new FormData()
    formData.append('file', file)

    try {
      // Step 1: Start import and get task_id
      const res = await fetch(`${API_BASE}/parse`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        const err = await res.json()
        setImportModal({
          show: true,
          status: 'error',
          step: 'Upload failed',
          progress: 0,
          error: err.detail || 'Unknown error'
        })
        return
      }

      const { task_id } = await res.json()

      // Step 2: Poll for progress
      const pollInterval = setInterval(async () => {
        try {
          const statusRes = await fetch(`${API_BASE}/parse/${task_id}`)
          if (!statusRes.ok) return

          const status = await statusRes.json()

          if (status.status === 'pending' || status.status === 'parsing') {
            setImportModal(prev => ({
              ...prev,
              status: 'processing',
              step: status.step || 'Processing...',
              progress: status.progress || 0,
              current: status.current,
              total: status.total
            }))
          } else if (status.status === 'complete') {
            clearInterval(pollInterval)
            setImportModal(prev => ({
              ...prev,
              status: 'complete',
              step: 'Import complete!',
              progress: 100,
              result: status.result
            }))
            setTimeout(() => {
              setImportModal({ show: false, status: 'uploading', step: '', progress: 0 })
              loadChats()
            }, 2000)
          } else if (status.status === 'error') {
            clearInterval(pollInterval)
            setImportModal(prev => ({
              ...prev,
              status: 'error',
              error: status.error || 'Unknown error'
            }))
          }
        } catch (err) {
          console.error('Poll error:', err)
        }
      }, 500)

    } catch (err) {
      setImportModal(prev => ({
        ...prev,
        status: 'error',
        error: err instanceof Error ? err.message : 'Upload failed'
      }))
    }
  }

  function handleSearchChange(value: string) {
    setSearch(value)
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current)
    searchTimeoutRef.current = setTimeout(() => {
      loadMessages(1)
    }, 300)
  }

  function handleUserFilter(userId: string) {
    setSelectedUser(userId)
    loadMessages(1, userId)
  }

  function handleContextMenu(e: React.MouseEvent, message: MessageBase) {
    e.preventDefault()
    setContextMenu({ x: e.clientX, y: e.clientY, message })
  }

  async function showMessageDetails(msg: MessageBase) {
    try {
      const res = await fetch(`${API_BASE}/messages/${msg.id}`)
      if (res.ok) {
        const data: MessageDetail = await res.json()
        setSelectedMessage(data)
        setShowJsonModal(true)
        setJsonContent(JSON.stringify(JSON.parse(data.raw_json), null, 2))
      }
    } catch (e) {
      console.error('Failed to load message details:', e)
    }
  }

  async function previewMedia(msg: MessageBase) {
    if (msg.file_type === 'text') return
    setMediaPreview({ type: msg.file_type, src: `${API_BASE}/media/${msg.id}` })
  }

  async function showContext(msg: MessageBase, count?: number) {
    const effectiveCount = count ?? contextModal.count
    console.log('showContext called with msg.id:', msg.id, 'count:', effectiveCount)
    setContextModal(prev => ({ ...prev, show: true, targetMsg: msg, before: [], after: [], loading: true, count: effectiveCount }))
    try {
      const res = await fetch(`${API_BASE}/messages/${msg.id}/context?count=${effectiveCount}`)
      console.log('Context API response status:', res.status)
      if (!res.ok) {
        console.error('Context API error:', res.status)
        setContextModal(prev => ({ ...prev, loading: false }))
        return
      }
      const data = await res.json()
      console.log('Context API data - before:', data.before?.length, 'after:', data.after?.length)
      setContextModal(prev => ({
        ...prev,
        before: data.before || [],
        after: data.after || [],
        loading: false
      }))
    } catch (e) {
      console.error('Failed to load context:', e)
      setContextModal(prev => ({ ...prev, loading: false }))
    }
  }

  function changeContextCount(count: number) {
    if (contextModal.targetMsg) {
      showContext(contextModal.targetMsg, count)
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text)
    setContextMenu(null)
  }

  function toggleTheme() {
    setTheme(t => t === 'light' ? 'dark' : 'light')
  }

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>Chats</h1>
          <button className="theme-toggle" onClick={toggleTheme}>
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          onChange={handleFileUpload}
          style={{ display: 'none' }}
        />
        <button
          className="upload-btn"
          onClick={() => fileInputRef.current?.click()}
        >
          + Import JSON
        </button>

        <div className="chat-list">
          {chats.map(chat => (
            <div
              key={chat.chat_id}
              className={`chat-item ${currentChat?.chat_id === chat.chat_id ? 'active' : ''}`}
              onClick={() => setCurrentChat(chat)}
            >
              <div className="chat-item-name">{chat.name}</div>
              <div className="chat-item-meta">{chat.message_count} messages</div>
            </div>
          ))}
          {chats.length === 0 && (
            <div className="empty-state">No chats imported</div>
          )}
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        {currentChat ? (
          <>
            <header className="header">
              <h1>{currentChat.name}</h1>
              <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
                {total} messages
              </span>
            </header>

            <div className="toolbar">
              <input
                type="text"
                className="search-input"
                placeholder="Search messages..."
                value={search}
                onChange={e => handleSearchChange(e.target.value)}
              />
              <div className="user-filter-wrapper">
                <input
                  type="text"
                  className="user-filter-input"
                  placeholder="Filter by user ID..."
                  list="user-list"
                  value={selectedUser}
                  onChange={e => handleUserFilter(e.target.value)}
                />
                <datalist id="user-list">
                  <option value="">All users</option>
                  {users.map(u => (
                    <option key={u.user_id} value={u.user_id}>
                      {u.name} ({u.message_count})
                    </option>
                  ))}
                </datalist>
              </div>
            </div>

            {loading ? (
              <div className="loading">Loading...</div>
            ) : messages.length === 0 ? (
              <div className="empty-state">No messages found</div>
            ) : (
              <>
                <div className="messages-container">
                  {messages.map(msg => (
                    <MessageBubble
                      key={msg.id}
                      message={msg}
                      onContextMenu={handleContextMenu}
                      onMediaClick={() => previewMedia(msg)}
                    />
                  ))}
                  <div ref={messagesEndRef} />
                </div>

                {totalPages > 1 && (
                  <div className="pagination">
                    <button disabled={page <= 1} onClick={() => loadMessages(1)}>
                      First
                    </button>
                    <button disabled={page <= 1} onClick={() => loadMessages(page - 1)}>
                      Previous
                    </button>
                    <span>
                      <input
                        type="number"
                        min={1}
                        max={totalPages}
                        defaultValue={page}
                        onKeyDown={e => {
                          if (e.key === 'Enter') {
                            const input = e.target as HTMLInputElement
                            const newPage = parseInt(input.value)
                            if (newPage >= 1 && newPage <= totalPages) {
                              loadMessages(newPage)
                            } else {
                              input.value = String(page)
                            }
                          }
                        }}
                        style={{
                          width: '60px',
                          padding: '4px 8px',
                          border: '1px solid var(--border)',
                          borderRadius: '4px',
                          textAlign: 'center',
                          background: 'var(--bg-primary)',
                          color: 'var(--text-primary)'
                        }}
                      />
                      {' '}of {totalPages}
                    </span>
                    <button disabled={page >= totalPages} onClick={() => loadMessages(page + 1)}>
                      Next
                    </button>
                    <button disabled={page >= totalPages} onClick={() => loadMessages(totalPages)}>
                      Last
                    </button>
                    <span style={{ marginLeft: '16px' }}>
                      Per page:
                      <select
                        value={pageSize}
                        onChange={e => {
                          const newSize = Number(e.target.value)
                          setPageSize(newSize)
                          loadMessages(1, undefined, newSize)
                        }}
                        style={{
                          marginLeft: '8px',
                          padding: '4px 8px',
                          border: '1px solid var(--border)',
                          borderRadius: '4px',
                          background: 'var(--bg-primary)',
                          color: 'var(--text-primary)'
                        }}
                      >
                        <option value={50}>50</option>
                        <option value={100}>100</option>
                        <option value={200}>200</option>
                        <option value={500}>500</option>
                      </select>
                    </span>
                  </div>
                )}
              </>
            )}
          </>
        ) : (
          <div className="empty-state">
            Select a chat from the sidebar or import a JSON file
          </div>
        )}
      </main>

      {/* Import Progress Modal */}
      {importModal.show && (
        <div className="modal-overlay">
          <div className="modal import-modal">
            <div className="modal-header">
              <h2>
                {importModal.status === 'complete' ? '✅ Import Complete' :
                 importModal.status === 'error' ? '❌ Import Failed' :
                 '📥 Importing...'}
              </h2>
            </div>
            <div className="modal-body">
              <div className="import-step">{importModal.step}</div>

              {importModal.current !== undefined && importModal.total !== undefined && (
                <div className="import-count">
                  {importModal.current} / {importModal.total} messages
                </div>
              )}

              {importModal.status !== 'complete' && importModal.status !== 'error' && (
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${importModal.progress}%` }}
                  />
                </div>
              )}

              {importModal.status !== 'complete' && importModal.status !== 'error' && (
                <div className="import-progress-text">{importModal.progress}%</div>
              )}

              {importModal.result && (
                <div className="import-result">
                  <p><strong>Chat Name:</strong> {importModal.result.chat_name}</p>
                  <p><strong>Messages:</strong> {importModal.result.message_count}</p>
                  <p><strong>Users:</strong> {importModal.result.user_count}</p>
                </div>
              )}

              {importModal.error && (
                <div className="import-error">
                  <strong>Error:</strong> {importModal.error}
                </div>
              )}

              {(importModal.status === 'complete' || importModal.status === 'error') && (
                <button
                  className="upload-btn"
                  onClick={() => setImportModal({ show: false, status: 'uploading', step: '', progress: 0 })}
                  style={{ marginTop: '16px' }}
                >
                  Close
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          message={contextMenu.message}
          onShowDetails={() => {
            showMessageDetails(contextMenu.message)
            setContextMenu(null)
          }}
          onCopyText={() => copyToClipboard(contextMenu.message.text)}
          onCopyJson={async () => {
            const res = await fetch(`${API_BASE}/messages/${contextMenu.message.id}`)
            if (res.ok) {
              const data = await res.json()
              copyToClipboard(data.raw_json)
            }
          }}
          onFilterUser={(userId) => {
            setContextMenu(null)
            setSelectedUser(userId)
            loadMessages(1, userId)
          }}
          onShowContext={() => {
            const msg = contextMenu.message
            setContextMenu(null)
            setTimeout(() => showContext(msg), 0)
          }}
        />
      )}

      {showJsonModal && selectedMessage && (
        <JsonModal
          message={selectedMessage}
          jsonContent={jsonContent}
          onClose={() => {
            setShowJsonModal(false)
            setSelectedMessage(null)
          }}
        />
      )}

      {mediaPreview && (
        <MediaPreviewModal
          type={mediaPreview.type}
          src={mediaPreview.src}
          onClose={() => setMediaPreview(null)}
        />
      )}

      {contextModal.show && (
        <ContextModal
          targetMsg={contextModal.targetMsg}
          before={contextModal.before}
          after={contextModal.after}
          loading={contextModal.loading}
          count={contextModal.count}
          onCountChange={changeContextCount}
          onClose={() => setContextModal(prev => ({ ...prev, show: false }))}
        />
      )}
    </div>
  )
}

function MessageBubble({
  message,
  onContextMenu,
  onMediaClick,
}: {
  message: MessageBase
  onContextMenu: (e: React.MouseEvent, msg: MessageBase) => void
  onMediaClick: () => void
}) {
  const bubbleClass = message.is_channel_forward ? 'channel' : 'other';

  // Generate avatar color from user_id
  const avatarBg = message.user_id
    ? `hsl(${Math.abs(hashCode(message.user_id)) % 360}, 60%, 50%)`
    : '#888';

  function hashCode(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return hash;
  }

  const displayId = message.user_id
    ? message.user_id.length > 8
      ? message.user_id.slice(0, 8)
      : message.user_id
    : '?';

  return (
    <div
      className={`message-bubble ${bubbleClass}`}
      onContextMenu={e => onContextMenu(e, message)}
    >
      <div className="message-avatar" style={{ backgroundColor: avatarBg }}>
        <span className="avatar-id">{displayId}</span>
      </div>
      <div className="message-content">
        {message.is_channel_forward && (
          <div className="sender">📢 Channel Forward</div>
        )}
        {message.user_name && !message.is_channel_forward && (
          <div className="sender">{message.user_name}</div>
        )}
        {message.text && <div className="text">{message.text}</div>}
        {message.file_type !== 'text' && message.file_type !== 'voice' && (
          message.thumb_data ? (
            <img
              className="media"
              src={`data:image/jpeg;base64,${message.thumb_data}`}
              alt={message.file_name || 'thumb'}
              style={{ maxWidth: message.thumb_w ? Math.min(message.thumb_w, 300) : 200, maxHeight: 200 }}
              onClick={onMediaClick}
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none'
              }}
            />
          ) : (
            <img
              className="media"
              src={`/api/media/${message.id}`}
              alt={message.file_name || 'media'}
              onClick={onMediaClick}
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none'
              }}
            />
          )
        )}
      {message.file_type === 'voice' && (
        <audio className="voice" controls src={`/api/media/${message.id}`} />
      )}
      <div className="time">{formatTime(message.date)}</div>
      </div>
    </div>
  )
}

function ContextMenu({
  x,
  y,
  message,
  onShowDetails,
  onCopyText,
  onCopyJson,
  onFilterUser,
  onShowContext,
}: {
  x: number
  y: number
  message: MessageBase
  onShowDetails: () => void
  onCopyText: () => void
  onCopyJson: () => void
  onFilterUser: (userId: string) => void
  onShowContext: () => void
}) {
  return (
    <div
      className="context-menu"
      style={{ left: x, top: y }}
      onClick={e => e.stopPropagation()}
    >
      <div className="context-menu-item" onClick={onShowDetails}>
        View Details
      </div>
      {message.text && (
        <div className="context-menu-item" onClick={onCopyText}>
          Copy Text
        </div>
      )}
      <div className="context-menu-item" onClick={onCopyJson}>
        Copy Raw JSON
      </div>
      {message.user_id && (
        <>
          <div className="context-menu-divider" />
          <div className="context-menu-item" onClick={() => onFilterUser(message.user_id!)}>
            Only show this user
          </div>
        </>
      )}
      <div className="context-menu-divider" />
      <div className="context-menu-item" onClick={onShowContext}>
        Show Context
      </div>
    </div>
  )
}

function JsonModal({
  message,
  jsonContent,
  onClose,
}: {
  message: MessageDetail
  jsonContent: string
  onClose: () => void
}) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Message Details</h2>
          <button className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">
          <div style={{ marginBottom: '12px' }}>
            <strong>ID:</strong> {message.msg_id}
          </div>
          <div style={{ marginBottom: '12px' }}>
            <strong>Sender:</strong> {message.user_name || message.user_id || 'Unknown'}
          </div>
          <div style={{ marginBottom: '12px' }}>
            <strong>Time:</strong> {formatDate(message.date)} {formatTime(message.date)}
          </div>
          <div style={{ marginBottom: '12px' }}>
            <strong>Type:</strong> {message.file_type}
          </div>
          {message.text && (
            <div style={{ marginBottom: '12px' }}>
              <strong>Text:</strong>
              <div
                style={{
                  background: 'var(--bg-secondary)',
                  padding: '8px',
                  borderRadius: '4px',
                  marginTop: '4px',
                }}
              >
                {message.text}
              </div>
            </div>
          )}
          <div style={{ marginBottom: '12px' }}>
            <strong>Raw JSON:</strong>
            <pre className="json-viewer">{jsonContent}</pre>
          </div>
        </div>
      </div>
    </div>
  )
}

function MediaPreviewModal({
  type,
  src,
  onClose,
}: {
  type: string
  src: string
  onClose: () => void
}) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal media-preview-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{type.charAt(0).toUpperCase() + type.slice(1)} Preview</h2>
          <button className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">
          {type === 'image' && <img src={src} alt="preview" style={{ maxWidth: '100%' }} />}
          {type === 'voice' && (
            <audio className="audio-preview" controls src={src} />
          )}
          {(type === 'video' || type === 'sticker') && (
            <video controls src={src} style={{ maxWidth: '100%' }} />
          )}
        </div>
      </div>
    </div>
  )
}

function ContextModal({
  targetMsg,
  before,
  after,
  loading,
  count,
  onCountChange,
  onClose,
}: {
  targetMsg: MessageBase | null
  before: MessageBase[]
  after: MessageBase[]
  loading: boolean
  count: number
  onCountChange: (count: number) => void
  onClose: () => void
}) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '700px', maxHeight: '85vh' }}>
        <div className="modal-header">
          <h2>Context ({before.length} before / {after.length} after)</h2>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <select
              value={count}
              onChange={e => onCountChange(Number(e.target.value))}
              style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
            >
              <option value={30}>30</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
            <button className="modal-close" onClick={onClose}>×</button>
          </div>
        </div>
        <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
          {loading ? (
            <div className="loading">Loading context...</div>
          ) : (
            <>
              {before.map(msg => (
                <ContextMessageBubble key={msg.id} message={msg} isTarget={false} />
              ))}
              {targetMsg && <ContextMessageBubble message={targetMsg} isTarget={true} />}
              {after.map(msg => (
                <ContextMessageBubble key={msg.id} message={msg} isTarget={false} />
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function ContextMessageBubble({ message, isTarget }: { message: MessageBase; isTarget: boolean }) {
  const bubbleClass = message.is_channel_forward ? 'channel' : 'other';

  const avatarBg = message.user_id
    ? `hsl(${Math.abs(hashCode(message.user_id)) % 360}, 60%, 50%)`
    : '#888';

  function hashCode(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return hash;
  }

  const displayId = message.user_id
    ? message.user_id.length > 8
      ? message.user_id.slice(0, 8)
      : message.user_id
    : '?';

  return (
    <div
      className={`message-bubble ${bubbleClass}`}
      style={{
        margin: '8px 0',
        border: isTarget ? '2px solid var(--accent)' : 'none',
        backgroundColor: isTarget ? 'var(--bubble-self)' : undefined
      }}
    >
      <div className="message-avatar" style={{ backgroundColor: avatarBg }}>
        <span className="avatar-id">{displayId}</span>
      </div>
      <div className="message-content">
        {message.is_channel_forward && (
          <div className="sender">📢 Channel Forward</div>
        )}
        {message.user_name && !message.is_channel_forward && (
          <div className="sender">{message.user_name}</div>
        )}
        {message.text && <div className="text">{message.text}</div>}
        {message.file_type !== 'text' && message.file_type !== 'voice' && (
          message.thumb_data ? (
            <img
              className="media"
              src={`data:image/jpeg;base64,${message.thumb_data}`}
              alt={message.file_name || 'thumb'}
              style={{ maxWidth: message.thumb_w ? Math.min(message.thumb_w, 200) : 150, maxHeight: 150 }}
            />
          ) : (
            <img
              className="media"
              src={`/api/media/${message.id}`}
              alt={message.file_name || 'media'}
            />
          )
        )}
        {message.file_type === 'voice' && (
          <audio className="voice" controls src={`/api/media/${message.id}`} />
        )}
        <div className="time">{formatTime(message.date)}</div>
      </div>
    </div>
  )
}
