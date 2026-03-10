import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listUsers, createUser, updateUser, UserItem } from '../api/users'

const ROLE_CONFIG: Record<string, { label: string; style: React.CSSProperties }> = {
  admin:     { label: 'Admin',     style: { background: '#1e3a8a', color: '#93c5fd' } },
  moderator: { label: 'Mod',       style: { background: '#3b0764', color: '#d8b4fe' } },
  user:      { label: 'User',      style: { background: '#1c1917', color: '#78716c' } },
}

function RoleBadge({ role }: { role: string }) {
  const cfg = ROLE_CONFIG[role] ?? { label: role, style: { background: '#222', color: '#aaa' } }
  return <span style={{ ...styles.badge, ...cfg.style }}>{cfg.label}</span>
}

function CreateUserForm({ onCreated }: { onCreated: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('user')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handle(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await createUser({ username, password, email: email || undefined, role })
      setUsername('')
      setPassword('')
      setEmail('')
      setRole('user')
      onCreated()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      let msg = 'Failed to create user'
      if (typeof detail === 'string') {
        msg = detail
      } else if (Array.isArray(detail) && detail.length > 0) {
        msg = detail.map((d: { msg?: string }) => d.msg ?? '').filter(Boolean).join('; ')
      }
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handle} style={styles.createForm}>
      <div style={styles.formRow}>
        <input
          style={styles.input}
          placeholder="Username *"
          value={username}
          onChange={e => setUsername(e.target.value)}
          required
          autoComplete="off"
        />
        <input
          style={styles.input}
          placeholder="Password *"
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          required
          autoComplete="new-password"
        />
        <input
          style={styles.input}
          placeholder="Email (optional)"
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
        />
        <select style={styles.select} value={role} onChange={e => setRole(e.target.value)}>
          <option value="user">User</option>
          <option value="moderator">Moderator</option>
          <option value="admin">Admin</option>
        </select>
        <button style={styles.createBtn} type="submit" disabled={loading}>
          {loading ? '...' : 'Create'}
        </button>
      </div>
      {error && <div style={styles.formError}>{error}</div>}
    </form>
  )
}

function PasswordModal({
  user,
  onClose,
  onSaved,
}: {
  user: UserItem
  onClose: () => void
  onSaved: () => void
}) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handle(e: React.FormEvent) {
    e.preventDefault()
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setError(null)
    setLoading(true)
    try {
      await updateUser(user.id, { password })
      onSaved()
      onClose()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to update password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={e => e.stopPropagation()}>
        <div style={styles.modalTitle}>Set password — {user.username}</div>
        <form onSubmit={handle}>
          <div style={styles.modalFields}>
            <input
              style={styles.input}
              placeholder="New password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              autoFocus
              autoComplete="new-password"
            />
            <input
              style={styles.input}
              placeholder="Confirm password"
              type="password"
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
            />
          </div>
          {error && <div style={styles.formError}>{error}</div>}
          <div style={styles.modalActions}>
            <button style={styles.createBtn} type="submit" disabled={loading}>
              {loading ? '...' : 'Save'}
            </button>
            <button style={styles.cancelBtn} type="button" onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function UserRow({
  user,
  onUpdate,
}: {
  user: UserItem
  onUpdate: () => void
}) {
  const [roleLoading, setRoleLoading] = useState(false)
  const [activeLoading, setActiveLoading] = useState(false)
  const [passwordTarget, setPasswordTarget] = useState(false)

  const lastLogin = user.last_login_at
    ? new Date(user.last_login_at).toLocaleDateString()
    : 'Never'

  async function handleRoleChange(role: string) {
    setRoleLoading(true)
    try {
      await updateUser(user.id, { role })
      onUpdate()
    } catch {
      // silently ignore — user may be changing own role which is blocked
    } finally {
      setRoleLoading(false)
    }
  }

  async function handleToggleActive() {
    setActiveLoading(true)
    try {
      await updateUser(user.id, { is_active: !user.is_active })
      onUpdate()
    } catch {
      // ignore self-deactivate guard
    } finally {
      setActiveLoading(false)
    }
  }

  return (
    <>
      <div style={user.is_active ? styles.row : { ...styles.row, opacity: 0.5 }}>
        <div style={styles.rowLeft}>
          <span style={styles.username}>{user.username}</span>
          {user.email && <span style={styles.email}>{user.email}</span>}
        </div>
        <div style={styles.rowMeta}>
          <span style={styles.metaItem}>Joined {new Date(user.created_at).toLocaleDateString()}</span>
          <span style={styles.metaDot}>·</span>
          <span style={styles.metaItem}>Last login {lastLogin}</span>
        </div>
        <div style={styles.rowRight}>
          <RoleBadge role={user.role} />
          <select
            style={styles.roleSelect}
            value={user.role}
            onChange={e => handleRoleChange(e.target.value)}
            disabled={roleLoading}
          >
            <option value="user">User</option>
            <option value="moderator">Moderator</option>
            <option value="admin">Admin</option>
          </select>
          <button
            style={styles.pwBtn}
            onClick={() => setPasswordTarget(true)}
          >
            Set password
          </button>
          <button
            style={user.is_active ? styles.deactivateBtn : styles.activateBtn}
            onClick={handleToggleActive}
            disabled={activeLoading}
          >
            {activeLoading ? '...' : user.is_active ? 'Deactivate' : 'Activate'}
          </button>
        </div>
      </div>
      {passwordTarget && (
        <PasswordModal
          user={user}
          onClose={() => setPasswordTarget(false)}
          onSaved={onUpdate}
        />
      )}
    </>
  )
}

export default function Users() {
  const [showCreate, setShowCreate] = useState(false)
  const queryClient = useQueryClient()

  const { data, isFetching, error } = useQuery({
    queryKey: ['users'],
    queryFn: listUsers,
    staleTime: 0,
  })

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ['users'] })
  }

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.heading}>Users</h1>
        {isFetching && <span style={styles.refreshing}>Refreshing...</span>}
        <button
          style={showCreate ? { ...styles.newBtn, ...styles.newBtnActive } : styles.newBtn}
          onClick={() => setShowCreate(v => !v)}
        >
          {showCreate ? 'Cancel' : '+ New user'}
        </button>
      </div>

      {showCreate && (
        <CreateUserForm
          onCreated={() => {
            refresh()
            setShowCreate(false)
          }}
        />
      )}

      {error && <div style={styles.error}>Failed to load users.</div>}

      <div style={styles.list}>
        {(data ?? []).map(user => (
          <UserRow key={user.id} user={user} onUpdate={refresh} />
        ))}
      </div>

      {!isFetching && (data ?? []).length === 0 && (
        <div style={styles.empty}>No users found.</div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    maxWidth: 900,
    margin: '0 auto',
    padding: '2rem 1rem',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    marginBottom: '1.5rem',
  },
  heading: {
    fontSize: '1.75rem',
    fontWeight: 700,
    color: '#f0f0f0',
    margin: 0,
    flex: 1,
  },
  refreshing: {
    fontSize: '0.8rem',
    color: '#555',
  },
  newBtn: {
    padding: '0.4rem 0.875rem',
    borderRadius: 6,
    border: '1px solid #333',
    background: '#1a1a1a',
    color: '#aaa',
    fontSize: '0.825rem',
    cursor: 'pointer',
  },
  newBtnActive: {
    border: '1px solid #555',
    color: '#f0f0f0',
  },
  createForm: {
    background: '#141414',
    border: '1px solid #2a2a2a',
    borderRadius: 8,
    padding: '1rem',
    marginBottom: '1.5rem',
  },
  formRow: {
    display: 'flex',
    gap: '0.75rem',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  input: {
    padding: '0.4rem 0.75rem',
    borderRadius: 6,
    border: '1px solid #333',
    background: '#1a1a1a',
    color: '#f0f0f0',
    fontSize: '0.875rem',
    minWidth: 160,
    flex: '1 1 160px',
  },
  select: {
    padding: '0.4rem 0.75rem',
    borderRadius: 6,
    border: '1px solid #333',
    background: '#1a1a1a',
    color: '#f0f0f0',
    fontSize: '0.875rem',
    cursor: 'pointer',
  },
  createBtn: {
    padding: '0.4rem 0.875rem',
    borderRadius: 6,
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    fontSize: '0.825rem',
    cursor: 'pointer',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  formError: {
    marginTop: '0.5rem',
    fontSize: '0.8rem',
    color: '#fca5a5',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.4rem',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    padding: '0.875rem 1rem',
    background: '#1a1a1a',
    border: '1px solid #2a2a2a',
    borderRadius: 8,
    flexWrap: 'wrap',
  },
  rowLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.15rem',
    flex: 1,
    minWidth: 120,
  },
  username: {
    fontWeight: 600,
    fontSize: '0.95rem',
    color: '#f0f0f0',
  },
  email: {
    fontSize: '0.775rem',
    color: '#666',
  },
  rowMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
    flexShrink: 0,
  },
  metaItem: {
    fontSize: '0.775rem',
    color: '#555',
  },
  metaDot: {
    color: '#333',
    fontSize: '0.775rem',
  },
  rowRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
    flexShrink: 0,
    flexWrap: 'wrap',
  },
  badge: {
    padding: '0.2rem 0.5rem',
    borderRadius: 4,
    fontSize: '0.7rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    whiteSpace: 'nowrap',
  },
  roleSelect: {
    padding: '0.3rem 0.5rem',
    borderRadius: 5,
    border: '1px solid #333',
    background: '#111',
    color: '#aaa',
    fontSize: '0.775rem',
    cursor: 'pointer',
  },
  pwBtn: {
    padding: '0.3rem 0.65rem',
    borderRadius: 5,
    border: '1px solid #333',
    background: 'transparent',
    color: '#888',
    fontSize: '0.775rem',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  deactivateBtn: {
    padding: '0.3rem 0.65rem',
    borderRadius: 5,
    border: '1px solid #7c3030',
    background: 'transparent',
    color: '#f87171',
    fontSize: '0.775rem',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  activateBtn: {
    padding: '0.3rem 0.65rem',
    borderRadius: 5,
    border: '1px solid #14532d',
    background: 'transparent',
    color: '#86efac',
    fontSize: '0.775rem',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  cancelBtn: {
    padding: '0.4rem 0.875rem',
    borderRadius: 6,
    border: '1px solid #333',
    background: 'transparent',
    color: '#888',
    fontSize: '0.825rem',
    cursor: 'pointer',
  },
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.6)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 100,
  },
  modal: {
    background: '#1a1a1a',
    border: '1px solid #2a2a2a',
    borderRadius: 10,
    padding: '1.5rem',
    width: 340,
    maxWidth: '90vw',
  },
  modalTitle: {
    fontSize: '1rem',
    fontWeight: 600,
    color: '#f0f0f0',
    marginBottom: '1rem',
  },
  modalFields: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
    marginBottom: '1rem',
  },
  modalActions: {
    display: 'flex',
    gap: '0.5rem',
    justifyContent: 'flex-end',
  },
  error: {
    color: '#ef4444',
    padding: '1rem',
    background: '#1a1a1a',
    borderRadius: 8,
    marginBottom: '1rem',
  },
  empty: {
    color: '#555',
    textAlign: 'center',
    padding: '3rem 1rem',
  },
}
