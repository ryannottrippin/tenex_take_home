function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
      <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908C16.658 14.013 17.64 11.705 17.64 9.2z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853"/>
      <path d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.961H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.039l3.007-2.332z" fill="#FBBC05"/>
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.961L3.964 6.293C4.672 4.166 6.656 3.58 9 3.58z" fill="#EA4335"/>
    </svg>
  )
}

export default function AuthScreen() {
  return (
    <div className="auth-screen">

      <div className="auth-left">
        <div className="auth-left-content">
          <div className="brand">
            <span className="brand-icon">◆</span>
            <span className="brand-name">DriveChat</span>
          </div>
          <h1>Your documents,<br />finally answerable.</h1>
          <p>Connect your Google Drive and ask questions across all your files. Get instant answers with citations.</p>
          <div className="feature-list">
            <div className="feature">
              <span>⚡</span>
              <span>Instant answers from any file</span>
            </div>
            <div className="feature">
              <span>📎</span>
              <span>Source citations included</span>
            </div>
            <div className="feature">
              <span>🔒</span>
              <span>Secure Google OAuth 2.0</span>
            </div>
          </div>
        </div>
      </div>

      <div className="auth-right">
        <div className="auth-card">
          <h2>Get started</h2>
          <p className="auth-subtitle">Sign in with your Google account to connect your Drive</p>
          <button className="google-btn" onClick={() => window.location.href = 'http://localhost:8000/auth/google'}>
            <GoogleIcon />
            Continue with Google
          </button>
          <p className="auth-disclaimer">
            By signing in, you allow read-only access to your Google Drive files.
          </p>
        </div>
      </div>

    </div>
  )
}
