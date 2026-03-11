import { api } from './client'

export interface AppSettings {
  registration_enabled: boolean
  require_approval: boolean
  library_folder_pattern: string
  file_naming_pattern: string
  jellyfin_external_url: string
  jellyfin_scan_interval: number
}

export interface ScanResult {
  synced: number
  resolved: number
}

export async function getSettings(): Promise<AppSettings> {
  const res = await api.get<AppSettings>('/settings')
  return res.data
}

export async function updateSettings(data: Partial<AppSettings>): Promise<AppSettings> {
  const res = await api.patch<AppSettings>('/settings', data)
  return res.data
}

export async function triggerScan(): Promise<ScanResult> {
  const res = await api.post<ScanResult>('/library/scan')
  return res.data
}

export async function getRegistrationStatus(): Promise<{ registration_enabled: boolean }> {
  const res = await api.get<{ registration_enabled: boolean }>('/auth/registration-status')
  return res.data
}
