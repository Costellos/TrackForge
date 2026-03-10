import { api } from './client'

export interface User {
  id: string
  username: string
  email: string | null
  role: string
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export async function register(username: string, password: string, email?: string): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>('/auth/register', { username, password, email })
  return res.data
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>('/auth/login', { username, password })
  return res.data
}

export async function getMe(): Promise<User> {
  const res = await api.get<User>('/auth/me')
  return res.data
}
