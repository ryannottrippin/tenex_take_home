import { useState, useEffect } from 'react'
import AuthScreen from './components/AuthScreen'
import DriveInput from './components/DriveInput'
import ChatInterface from './components/ChatInterface'

function App() {
  const [screen, setScreen] = useState('loading')
  const [user, setUser] = useState(null)
  const [folderLink, setFolderLink] = useState('')

  useEffect(() => {
    fetch('http://localhost:8000/auth/me', { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        if (data.user) {
          setUser(data.user)
          setScreen('drive')
        } else {
          setScreen('auth')
        }
      })
      .catch(() => setScreen('auth'))
  }, [])

  if (screen === 'loading') return null
  if (screen === 'auth') return <AuthScreen />
  if (screen === 'drive') return <DriveInput user={user} onSubmit={link => { setFolderLink(link); setScreen('chat') }} />
  if (screen === 'chat') return <ChatInterface user={user} folderLink={folderLink} />
}

export default App
