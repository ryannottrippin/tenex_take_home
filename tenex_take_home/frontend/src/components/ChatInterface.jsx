import { useState, useEffect, useRef } from 'react'
import { getFiles } from '../api/drive'
import { sendMessage } from '../api/chat'

function fileIcon(mimeType) {
  if (mimeType === 'application/vnd.google-apps.document') return '📄'
  if (mimeType === 'application/vnd.google-apps.spreadsheet') return '📊'
  if (mimeType === 'application/vnd.google-apps.presentation') return '📋'
  if (mimeType === 'application/pdf') return '📕'
  if (mimeType?.startsWith('image/')) return '🖼️'
  return '📎'
}

export default function ChatInterface({ user, folderLink }) {
  const [files, setFiles] = useState(null)       // null = loading
  const [folderName, setFolderName] = useState('Folder')
  const [filesError, setFilesError] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef(null)

  const initials = user?.name
    ? user.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : user?.email?.[0]?.toUpperCase() ?? '?'

  // Load files on mount
  useEffect(() => {
    getFiles(folderLink)
      .then(data => {
        setFolderName(data.folder_name || 'Folder')
        setFiles(data.files || [])
      })
      .catch(err => setFilesError(err.message || 'Could not connect to server'))
  }, [folderLink])

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  const handleSend = async () => {
    if (!input.trim() || sending) return
    const text = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text }])
    setSending(true)

    try {
      const data = await sendMessage(folderLink, text, messages)
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: data.answer,
        citations: data.citations || [],
      }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', text: err.message || 'Something went wrong. Please try again.' }])
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="chat-layout">

      {/* Sidebar */}
      <div className="sidebar">
        <div className="sidebar-header">
          <span className="brand-icon">◆</span>
          <span className="brand-name">DriveChat</span>
        </div>

        <div className="sidebar-folder">
          <div className="sidebar-label">Connected Folder</div>
          <div className="sidebar-folder-name">{folderName}</div>
        </div>

        <div className="sidebar-files">
          <div className="sidebar-label" style={{ marginBottom: '0.75rem' }}>Files</div>
          {files === null && !filesError && (
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Loading...</div>
          )}
          {filesError && (
            <div style={{ fontSize: '0.8rem', color: '#ef4444' }}>{filesError}</div>
          )}
          {files && files.length === 0 && (
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No files found</div>
          )}
          {files && files.map(file => (
            <div key={file.id} className="file-item">
              <span style={{ fontSize: '0.85rem', flexShrink: 0 }}>{fileIcon(file.mimeType)}</span>
              <span className="file-name">{file.name}</span>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="avatar-sm">{initials}</div>
            <span className="sidebar-user-email">{user?.email}</span>
          </div>
        </div>
      </div>

      {/* Main chat area */}
      <div className="chat-main">
        <div className="chat-header">
          <div>
            <h3>Ask about your files</h3>
            <span className="chat-subtitle">
              {files === null ? 'Loading files...' : `${files.length} file${files.length !== 1 ? 's' : ''} indexed`}
            </span>
          </div>
        </div>

        <div className="messages-container">
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '4rem' }}>
              <p style={{ fontSize: '0.9rem' }}>Ask anything about the files in this folder.</p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`message message-${msg.role}`}>
              <div className={`message-avatar ${msg.role === 'assistant' ? 'assistant-avatar' : 'user-avatar'}`}>
                {msg.role === 'assistant' ? '◆' : initials}
              </div>
              <div className="message-bubble">
                <p>{msg.text}</p>
                {msg.citations && msg.citations.length > 0 && (
                  <div className="citations-block">
                    <div className="citations">
                      {msg.citations.map((c, j) => (
                        <a
                          key={j}
                          className="citation"
                          href={`https://drive.google.com/file/d/${c.id}/view`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <span className="citation-num">{j + 1}</span>
                          {c.name}{c.page_label ? ` (${c.page_label})` : ''}
                        </a>
                      ))}
                    </div>
                    {msg.citations.some(c => c.passage) && (
                      <details className="passages">
                        <summary>View source passages</summary>
                        {msg.citations.filter(c => c.passage).map((c, j) => (
                          <div key={j} className="passage">
                            <span className="passage-file">
                              {c.name}{c.page_label ? ` — ${c.page_label}` : ''}
                            </span>
                            <p>{c.passage}</p>
                          </div>
                        ))}
                      </details>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {sending && (
            <div className="message message-assistant">
              <div className="message-avatar assistant-avatar">◆</div>
              <div className="message-bubble">
                <p style={{ color: 'var(--text-muted)' }}>Thinking...</p>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-bar">
          <textarea
            className="chat-input"
            placeholder="Ask a question about your files..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            rows={1}
          />
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={!input.trim() || sending}
          >
            ↑
          </button>
        </div>
      </div>

    </div>
  )
}
