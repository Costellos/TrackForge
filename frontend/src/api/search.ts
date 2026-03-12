import { api } from './client'

export type SearchType = 'artist' | 'album' | 'song'

export interface ArtistResult {
  mbid: string | null
  name: string | null
  sort_name: string | null
  disambiguation: string | null
  type: string | null
  country: string | null
  begin: string | null
  end: string | null
  score: number | null
}

export interface ReleaseGroupResult {
  mbid: string | null
  title: string | null
  type: string | null
  secondary_types: string[]
  first_release_date: string | null
  artists: { mbid: string; name: string }[]
  score: number | null
  track_count: number | null
}

export interface RecordingResult {
  mbid: string | null
  title: string | null
  length_ms: number | null
  disambiguation: string | null
  artists: { mbid: string; name: string }[]
  releases: { mbid: string; title: string; date: string }[]
  score: number | null
  isrcs: string[]
}

export type SearchResult = ArtistResult | ReleaseGroupResult | RecordingResult

export interface SearchResponse {
  query: string
  type: SearchType
  results: SearchResult[]
}

export async function search(q: string, type: SearchType, limit = 20): Promise<SearchResponse> {
  const res = await api.get<SearchResponse>('/search', { params: { q, type, limit } })
  return res.data
}

export interface ArtistDetail extends ArtistResult {
  release_groups: ReleaseGroupResult[]
  image_thumb: string | null
  image_background: string | null
}

export async function getArtist(mbid: string): Promise<ArtistDetail> {
  const res = await api.get(`/search/artist/${mbid}`)
  return res.data
}

export interface ArtistImages {
  mbid: string
  thumb: string | null
  background: string | null
}

export async function getArtistImages(mbid: string): Promise<ArtistImages> {
  const res = await api.get<ArtistImages>(`/search/artist/${mbid}/images`)
  return res.data
}

export async function getReleaseGroup(mbid: string): Promise<ReleaseGroupResult & { releases: object[] }> {
  const res = await api.get(`/search/album/${mbid}`)
  return res.data
}

export interface TrackResult {
  disc: number
  position: number
  number: string
  title: string
  length_ms: number | null
  recording_mbid: string | null
}

export interface ReleaseOption {
  mbid: string
  label: string
}

export interface AlbumTracksResult {
  release_group_mbid: string
  release_mbid?: string
  album_title: string
  album_type: string | null
  album_secondary_types: string[]
  first_release_date: string | null
  artists: { mbid: string; name: string }[]
  tracks: TrackResult[]
  releases?: ReleaseOption[]
}

export async function getAlbumTracks(mbid: string, releaseMbid?: string): Promise<AlbumTracksResult> {
  const params = releaseMbid ? { release_mbid: releaseMbid } : {}
  const res = await api.get<AlbumTracksResult>(`/search/album/${mbid}/tracks`, { params })
  return res.data
}

export interface PreviewResult {
  source: 'spotify' | 'itunes' | 'youtube' | 'none'
  url: string | null
}

export async function getTrackPreview(recordingMbid: string): Promise<PreviewResult> {
  const res = await api.get<PreviewResult>(`/search/preview/${recordingMbid}`)
  return res.data
}
