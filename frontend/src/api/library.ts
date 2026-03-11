import { api } from './client'

export interface RecentlyAddedItem {
  jellyfin_item_id: string | null
  name: string
  artist_name: string
  mbid: string | null
  release_mbid: string | null
  artist_mbid: string | null
  year: number | null
  date_created: string | null
}

/** Build the best available cover art URL for a recently added item. */
export function recentlyAddedArtUrl(item: RecentlyAddedItem): string | null {
  if (item.mbid) return `https://coverartarchive.org/release-group/${item.mbid}/front-250`
  if (item.release_mbid) return `https://coverartarchive.org/release/${item.release_mbid}/front-250`
  if (item.jellyfin_item_id) return `${api.defaults.baseURL}/library/image/${item.jellyfin_item_id}`
  return null
}

export interface RecentlyAddedResponse {
  items: RecentlyAddedItem[]
  jellyfin_url: string | null
}

export async function getRecentlyAdded(limit = 20): Promise<RecentlyAddedResponse> {
  const res = await api.get<RecentlyAddedResponse>('/library/recently-added', { params: { limit } })
  return res.data
}

export async function resolveJellyfinItem(jellyfinItemId: string): Promise<string | null> {
  const res = await api.get<{ release_group_mbid: string | null }>(`/library/resolve/${jellyfinItemId}`)
  return res.data.release_group_mbid
}

export interface LibraryStatusResult {
  statuses: Record<string, string | null>
  jellyfin_url: string | null
}

export async function checkLibraryStatus(mbids: string[]): Promise<LibraryStatusResult> {
  if (mbids.length === 0) return { statuses: {}, jellyfin_url: null }
  const res = await api.post<LibraryStatusResult>('/library/status', { mbids })
  return res.data
}

/** Build the Jellyfin web URL for an item. */
export function jellyfinWebUrl(baseUrl: string, itemId: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/web/index.html#!/details?id=${itemId}`
}

export interface LibrarySearchItem {
  jellyfin_item_id: string
  name: string
  artist_name: string
  year: number | null
}

export async function searchLibrary(query: string): Promise<LibrarySearchItem[]> {
  const res = await api.get<{ items: LibrarySearchItem[] }>('/library/search', { params: { q: query } })
  return res.data.items
}
