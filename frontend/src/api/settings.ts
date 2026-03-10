import { api } from './client'

export interface AppSettings {
  registration_enabled: boolean
  require_approval: boolean
  library_folder_pattern: string
  file_naming_pattern: string
}

export async function getSettings(): Promise<AppSettings> {
  const res = await api.get<AppSettings>('/settings')
  return res.data
}

export async function updateSettings(data: Partial<AppSettings>): Promise<AppSettings> {
  const res = await api.patch<AppSettings>('/settings', data)
  return res.data
}

export async function getRegistrationStatus(): Promise<{ registration_enabled: boolean }> {
  const res = await api.get<{ registration_enabled: boolean }>('/auth/registration-status')
  return res.data
}
