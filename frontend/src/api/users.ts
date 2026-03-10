import { api } from './client'

export interface UserItem {
  id: string
  username: string
  email: string | null
  role: string
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

export async function listUsers(): Promise<UserItem[]> {
  const res = await api.get<UserItem[]>('/users')
  return res.data
}

export async function createUser(data: {
  username: string
  password: string
  email?: string
  role: string
}): Promise<UserItem> {
  const res = await api.post<UserItem>('/users', data)
  return res.data
}

export async function updateUser(
  id: string,
  data: { role?: string; is_active?: boolean; password?: string },
): Promise<UserItem> {
  const res = await api.patch<UserItem>(`/users/${id}`, data)
  return res.data
}
