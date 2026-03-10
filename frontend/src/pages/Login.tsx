import { useState, useEffect, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, register, getMe } from '../api/auth'
import { getRegistrationStatus } from '../api/settings'
import { useAuthStore } from '../stores/auth'

export default function Login() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [regEnabled, setRegEnabled] = useState<boolean | null>(null)

  const { setToken, setUser } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    getRegistrationStatus()
      .then(r => setRegEnabled(r.registration_enabled))
      .catch(() => setRegEnabled(false))
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const res = mode === 'login'
        ? await login(username, password)
        : await register(username, password, email || undefined)

      setToken(res.access_token)
      const user = await getMe()
      setUser(user)
      navigate('/')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={styles.brand}>TrackForge</h1>
        <p style={styles.sub}>
          {mode === 'login' ? 'Sign in to your account' : 'Create an account'}
        </p>

        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.field}>
            <label style={styles.label}>Username</label>
            <input
              style={styles.input}
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
              required
            />
          </div>

          {mode === 'register' && (
            <div style={styles.field}>
              <label style={styles.label}>Email (optional)</label>
              <input
                style={styles.input}
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
              />
            </div>
          )}

          <div style={styles.field}>
            <label style={styles.label}>Password</label>
            <input
              style={styles.input}
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>

          {error && <div style={styles.error}>{error}</div>}

          <button type="submit" style={styles.btn} disabled={loading}>
            {loading ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <div style={styles.toggle}>
          {mode === 'login' && regEnabled && (
            <>No account? <button style={styles.link} onClick={() => setMode('register')}>Register</button></>
          )}
          {mode === 'register' && (
            <>Already have an account? <button style={styles.link} onClick={() => setMode('login')}>Sign in</button></>
          )}
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#0f0f0f',
  },
  card: {
    width: '100%',
    maxWidth: 380,
    padding: '2rem',
    background: '#1a1a1a',
    border: '1px solid #2a2a2a',
    borderRadius: 12,
  },
  brand: {
    fontSize: '1.5rem',
    fontWeight: 700,
    color: '#2563eb',
    marginBottom: '0.25rem',
  },
  sub: {
    color: '#888',
    fontSize: '0.875rem',
    marginBottom: '1.5rem',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.35rem',
  },
  label: {
    fontSize: '0.8rem',
    color: '#aaa',
  },
  input: {
    padding: '0.6rem 0.75rem',
    borderRadius: 6,
    border: '1px solid #333',
    background: '#111',
    color: '#f0f0f0',
    fontSize: '0.95rem',
    outline: 'none',
  },
  error: {
    fontSize: '0.825rem',
    color: '#ef4444',
    background: '#1f0000',
    padding: '0.5rem 0.75rem',
    borderRadius: 6,
  },
  btn: {
    padding: '0.65rem',
    borderRadius: 6,
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    fontSize: '0.95rem',
    fontWeight: 600,
    cursor: 'pointer',
    marginTop: '0.25rem',
  },
  toggle: {
    marginTop: '1.25rem',
    textAlign: 'center',
    fontSize: '0.825rem',
    color: '#666',
  },
  link: {
    background: 'none',
    border: 'none',
    color: '#2563eb',
    cursor: 'pointer',
    fontSize: '0.825rem',
    padding: 0,
  },
}
