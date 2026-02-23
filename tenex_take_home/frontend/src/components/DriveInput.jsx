import { useState } from 'react'

export default function DriveInput({ user, onSubmit }) {
  const [link, setLink] = useState('')

  const initials = user?.name
    ? user.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : user?.email?.[0]?.toUpperCase() ?? '?'

  const handleSubmit = () => {
    if (link.trim()) onSubmit(link.trim())
  }

  return (
    <div className="drive-screen">

      <nav className="navbar">
        <div className="navbar-brand">
          <span className="brand-icon">◆</span>
          <span className="brand-name">DriveChat</span>
        </div>
        <div className="navbar-user">
          <span className="user-email">{user?.email}</span>
          <div className="avatar">{initials}</div>
        </div>
      </nav>

      <div className="drive-content">
        <div className="drive-card">
          <h2>Connect a Google Drive folder</h2>
          <p>Paste the link to any folder and start asking questions about your files.</p>
          <div className="link-input-row">
            <input
              className="link-input"
              type="text"
              placeholder="https://drive.google.com/drive/folders/..."
              value={link}
              onChange={e => setLink(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            />
            <button
              className="btn-primary"
              onClick={handleSubmit}
              disabled={!link.trim()}
            >
              Start
            </button>
          </div>
          <p className="input-hint">Supports folders and shared drives</p>
        </div>
      </div>

    </div>
  )
}
