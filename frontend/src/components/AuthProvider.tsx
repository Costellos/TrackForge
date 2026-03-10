import { useEffect } from 'react'
import { useLocation, Navigate } from 'react-router-dom'
import { getMe } from '../api/auth'
import { useAuthStore } from '../stores/auth'

/** Loads the current user on mount if a token exists. */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { token, setUser, logout } = useAuthStore()

  useEffect(() => {
    if (!token) return
    getMe()
      .then(setUser)
      .catch(() => logout())
  }, [token])

  return <>{children}</>
}

/** Redirects to /login if not authenticated. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore(s => s.token)
  const location = useLocation()

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}
