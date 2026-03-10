import { api } from './client'
import { ArtistResult, ReleaseGroupResult } from './search'

export interface RequestResponse {
  id: string
  target_type: string
  target_id: string
  status: string
  user_notes: string | null
  created_at: string
}

export async function requestArtist(artist: ArtistResult, notes?: string): Promise<RequestResponse> {
  const res = await api.post<RequestResponse>('/requests/artist', {
    mbid: artist.mbid,
    name: artist.name,
    sort_name: artist.sort_name,
    user_notes: notes,
  })
  return res.data
}

export async function requestCollection(album: ReleaseGroupResult, notes?: string): Promise<RequestResponse> {
  const primary = album.artists[0]
  const res = await api.post<RequestResponse>('/requests/collection', {
    mbid: album.mbid,
    title: album.title,
    type: album.type ?? 'album',
    first_release_date: album.first_release_date,
    artist_mbid: primary?.mbid ?? null,
    artist_name: primary?.name ?? null,
    user_notes: notes,
  })
  return res.data
}

export interface LibraryEntry {
  id: string
  target_type: string
  target_id: string
  status: string
  user_notes: string | null
  created_at: string
  name: string
  subtitle: string | null
  year: string | null
  requested_by: string | null
  mbid: string | null
}

export async function listLibrary(): Promise<LibraryEntry[]> {
  const res = await api.get<LibraryEntry[]>('/requests/library')
  return res.data
}

export async function listRequests(): Promise<RequestResponse[]> {
  const res = await api.get<RequestResponse[]>('/requests')
  return res.data
}

export async function approveRequest(id: string): Promise<RequestResponse> {
  const res = await api.post<RequestResponse>(`/requests/${id}/approve`)
  return res.data
}

export async function cancelRequest(id: string): Promise<RequestResponse> {
  const res = await api.post<RequestResponse>(`/requests/${id}/cancel`)
  return res.data
}

export async function retryRequest(id: string): Promise<RequestResponse> {
  const res = await api.post<RequestResponse>(`/requests/${id}/retry`)
  return res.data
}

export async function rejectRequest(id: string, adminNotes?: string): Promise<RequestResponse> {
  const res = await api.post<RequestResponse>(`/requests/${id}/reject`, { admin_notes: adminNotes ?? null })
  return res.data
}

export interface SongRequestParams {
  recording_mbid: string
  title: string
  artist_mbid: string | null
  artist_name: string | null
  length_ms: number | null
}

export async function requestSong(params: SongRequestParams, notes?: string): Promise<RequestResponse> {
  const res = await api.post<RequestResponse>('/requests/song', {
    ...params,
    user_notes: notes,
  })
  return res.data
}

export interface NzbCandidate {
  title: string
  download_url: string
  indexer: string
  size: number
  age_days: number
  grabs: number
  format_score: number
  score: number
  already_tried: boolean
}

export async function listCandidates(requestId: string, artistOverride?: string): Promise<NzbCandidate[]> {
  const params = artistOverride ? { artist_override: artistOverride } : undefined
  const res = await api.get<NzbCandidate[]>(`/requests/${requestId}/candidates`, { params })
  return res.data
}

export async function selectCandidate(requestId: string, downloadUrl: string, title: string): Promise<RequestResponse> {
  const res = await api.post<RequestResponse>(`/requests/${requestId}/select-candidate`, {
    download_url: downloadUrl,
    title,
  })
  return res.data
}

export async function checkMbidStatuses(mbids: string[]): Promise<Record<string, string | null>> {
  if (mbids.length === 0) return {}
  const res = await api.post<{ statuses: Record<string, string | null> }>('/requests/status', { mbids })
  return res.data.statuses
}
