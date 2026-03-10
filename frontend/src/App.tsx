import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import { AuthProvider, RequireAuth } from './components/AuthProvider'
import { useAuthStore } from './stores/auth'
import Search from './pages/Search'
import Library from './pages/Library'
import Admin from './pages/Admin'
import Users from './pages/Users'
import Login from './pages/Login'
import Home from './pages/Home'
import Settings from './pages/Settings'
import ArtistPage from './pages/ArtistPage'
import AlbumPage from './pages/AlbumPage'
import GlobalPlayer from './components/GlobalPlayer'

function Nav() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <nav style={styles.nav}>
      <span style={styles.brand}>TrackForge</span>
      <div style={styles.links}>
        <NavLink to="/" end style={({ isActive }) => isActive ? { ...styles.link, ...styles.linkActive } : styles.link}>
          Home
        </NavLink>
        <NavLink to="/search" style={({ isActive }) => isActive ? { ...styles.link, ...styles.linkActive } : styles.link}>
          Search
        </NavLink>
        <NavLink to="/library" style={({ isActive }) => isActive ? { ...styles.link, ...styles.linkActive } : styles.link}>
          Library
        </NavLink>
        {user?.role === 'admin' && (
          <>
            <NavLink to="/admin" style={({ isActive }) => isActive ? { ...styles.link, ...styles.linkActive } : styles.link}>
              Requests
            </NavLink>
            <NavLink to="/users" style={({ isActive }) => isActive ? { ...styles.link, ...styles.linkActive } : styles.link}>
              Users
            </NavLink>
            <NavLink to="/settings" style={({ isActive }) => isActive ? { ...styles.link, ...styles.linkActive } : styles.link}>
              Settings
            </NavLink>
          </>
        )}
      </div>
      <div style={styles.navRight}>
        {user && (
          <>
            <span style={styles.username}>{user.username}</span>
            {user.role === 'admin' && <span style={styles.badge}>admin</span>}
            <button style={styles.logoutBtn} onClick={handleLogout}>Sign out</button>
          </>
        )}
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <div style={styles.app}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/*"
            element={
              <RequireAuth>
                <>
                  <Nav />
                  <main style={styles.main}>
                    <Routes>
                      <Route path="/" element={<Home />} />
                      <Route path="/search" element={<Search />} />
                      <Route path="/artist/:mbid" element={<ArtistPage />} />
                      <Route path="/album/:mbid" element={<AlbumPage />} />
                      <Route path="/library" element={<Library />} />
                      <Route path="/admin" element={<Admin />} />
                      <Route path="/users" element={<Users />} />
                      <Route path="/settings" element={<Settings />} />
                    </Routes>
                  </main>
                  <GlobalPlayer />
                </>
              </RequireAuth>
            }
          />
        </Routes>
      </div>
    </AuthProvider>
  )
}

const styles: Record<string, React.CSSProperties> = {
  app: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
  },
  nav: {
    display: 'flex',
    alignItems: 'center',
    gap: '2rem',
    padding: '0 1.5rem',
    height: 52,
    background: '#111',
    borderBottom: '1px solid #222',
    position: 'sticky',
    top: 0,
    zIndex: 10,
  },
  brand: {
    fontWeight: 700,
    fontSize: '1rem',
    color: '#2563eb',
    letterSpacing: '-0.01em',
  },
  links: {
    display: 'flex',
    gap: '1.25rem',
    flex: 1,
  },
  link: {
    color: '#888',
    textDecoration: 'none',
    fontSize: '0.875rem',
  },
  linkActive: {
    color: '#f0f0f0',
  },
  navRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
  },
  username: {
    fontSize: '0.825rem',
    color: '#aaa',
  },
  badge: {
    fontSize: '0.7rem',
    padding: '0.15rem 0.5rem',
    borderRadius: 4,
    background: '#1e3a8a',
    color: '#93c5fd',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  logoutBtn: {
    padding: '0.3rem 0.75rem',
    borderRadius: 5,
    border: '1px solid #333',
    background: 'transparent',
    color: '#888',
    fontSize: '0.8rem',
    cursor: 'pointer',
  },
  main: {
    flex: 1,
    paddingBottom: 60,
  },
}
