import { api } from './client'

export interface TrendingReleaseGroup {
  release_group_mbid: string | null
  title: string | null
  artist_name: string | null
  artist_mbids: string[]
  listen_count: number | null
  caa_id: number | null
  caa_release_mbid: string | null
}

export interface TrendingArtist {
  artist_mbid: string | null
  artist_name: string | null
  listen_count: number | null
}

export async function getTrendingReleaseGroups(
  range: string = 'week',
  count: number = 20,
): Promise<TrendingReleaseGroup[]> {
  const res = await api.get<TrendingReleaseGroup[]>('/trending/release-groups', {
    params: { range, count },
  })
  return res.data
}

export async function getTrendingArtists(
  range: string = 'week',
  count: number = 20,
): Promise<TrendingArtist[]> {
  const res = await api.get<TrendingArtist[]>('/trending/artists', {
    params: { range, count },
  })
  return res.data
}
