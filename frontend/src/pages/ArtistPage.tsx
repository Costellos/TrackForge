import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getArtist, getAlbumTracks, ReleaseGroupResult } from '../api/search'
import { requestCollection, checkMbidStatuses } from '../api/requests'
import { checkLibraryStatus, jellyfinWebUrl } from '../api/library'
import PreviewButton from '../components/PreviewButton'

type RequestState = 'idle' | 'loading' | 'done' | 'duplicate' | 'error'

function statusToRequestState(status: string | null | undefined): RequestState {
  if (!status) return 'idle'
  if (status === 'available') return 'done'
  return 'duplicate'
}

function formatDuration(ms: number | null): string {
  if (!ms) return ''
  const total = Math.round(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function ArtistImage({ url, size }: { url: string | null | undefined; size: number }) {
  const [failed, setFailed] = useState(false)
  const box: React.CSSProperties = { width: size, height: size, borderRadius: '50%', flexShrink: 0, background: '#1e1e1e', border: '1px solid #2a2a2a' }
  if (!url || failed) return <div style={box} />
  return (
    <img
      src={url}
      alt=""
      onError={() => setFailed(true)}
      style={{ ...box, objectFit: 'cover', border: 'none' }}
    />
  )
}

function CoverArt({ mbid, size }: { mbid: string; size: number }) {
  const [failed, setFailed] = useState(false)
  const box: React.CSSProperties = { width: size, height: size, borderRadius: 4, flexShrink: 0, background: '#1e1e1e', border: '1px solid #2a2a2a' }
  if (failed) return <div style={box} />
  return (
    <img
      src={`https://coverartarchive.org/release-group/${mbid}/front-250`}
      alt=""
      onError={() => setFailed(true)}
      style={{ ...box, objectFit: 'cover', border: 'none' }}
    />
  )
}

function RequestButton({ onRequest, initialState = 'idle' }: { onRequest: () => Promise<void>; initialState?: RequestState }) {
  const [state, setState] = useState<RequestState>(initialState)

  useEffect(() => {
    if (initialState !== 'idle') setState(initialState)
  }, [initialState])

  async function handle() {
    setState('loading')
    try {
      await onRequest()
      setState('done')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setState(status === 409 ? 'duplicate' : 'error')
    }
  }

  if (state === 'done') return <span style={styles.requestedTag}>Requested</span>
  if (state === 'duplicate') return <span style={styles.duplicateTag}>Already requested</span>
  if (state === 'error') return <span style={styles.errorTag}>Error</span>

  return (
    <button style={styles.requestBtn} onClick={handle} disabled={state === 'loading'}>
      {state === 'loading' ? '...' : 'Request'}
    </button>
  )
}

function TrackList({ mbid }: { mbid: string }) {
  const { data, isFetching, error } = useQuery({
    queryKey: ['album-tracks', mbid],
    queryFn: () => getAlbumTracks(mbid),
    staleTime: 1000 * 60 * 5,
  })

  if (isFetching) return <div style={styles.trackLoading}>Loading tracks...</div>
  if (error) return <div style={styles.trackError}>Failed to load tracks.</div>
  if (!data) return null

  const discs = data.tracks.reduce<Record<number, typeof data.tracks>>((acc, t) => {
    const d = t.disc ?? 1
    if (!acc[d]) acc[d] = []
    acc[d].push(t)
    return acc
  }, {})
  const discNumbers = Object.keys(discs).map(Number).sort()
  const multiDisc = discNumbers.length > 1

  const artistName = data.artists?.map((a: { name: string }) => a.name).join(', ') ?? null

  return (
    <div style={styles.trackList}>
      {discNumbers.map(disc => (
        <div key={disc}>
          {multiDisc && <div style={styles.discLabel}>Disc {disc}</div>}
          {discs[disc].map((track, i) => (
            <div key={i} style={styles.trackRow}>
              <span style={styles.trackNum}>{track.number ?? track.position}</span>
              <PreviewButton recordingMbid={track.recording_mbid} title={track.title} artist={artistName} />
              <span style={styles.trackTitle}>{track.title}</span>
              <span style={styles.trackDuration}>{formatDuration(track.length_ms)}</span>
            </div>
          ))}
        </div>
      ))}
      {data.tracks.length === 0 && (
        <div style={styles.trackEmpty}>No track information available.</div>
      )}
    </div>
  )
}

export default function ArtistPage() {
  const { mbid } = useParams<{ mbid: string }>()
  const navigate = useNavigate()
  const [expandedMbid, setExpandedMbid] = useState<string | null>(null)

  const { data, isFetching, error } = useQuery({
    queryKey: ['artist', mbid],
    queryFn: () => getArtist(mbid!),
    enabled: !!mbid,
    staleTime: 1000 * 60 * 5,
  })

  const albums: ReleaseGroupResult[] = data?.release_groups ?? []
  const albumMbids = albums.map(a => a.mbid).filter((m): m is string => Boolean(m))

  const { data: statusData } = useQuery({
    queryKey: ['request-statuses', albumMbids],
    queryFn: () => checkMbidStatuses(albumMbids),
    enabled: albumMbids.length > 0,
    staleTime: 1000 * 30,
  })

  const { data: libraryResult } = useQuery({
    queryKey: ['library-statuses', albumMbids],
    queryFn: () => checkLibraryStatus(albumMbids),
    enabled: albumMbids.length > 0,
    staleTime: 1000 * 60 * 5,
  })

  function getGroup(album: ReleaseGroupResult): string {
    const t = album.type ?? ''
    if (t === 'Single') return 'Singles'
    if (t === 'EP') return 'EPs'
    if (t === 'Album' && album.secondary_types.length === 0) return 'Albums'
    if (t === 'Album') return 'Other'
    return 'Other'
  }

  const GROUP_ORDER = ['Albums', 'EPs', 'Singles', 'Other']

  function sortByDate(a: ReleaseGroupResult, b: ReleaseGroupResult) {
    if (!a.first_release_date) return 1
    if (!b.first_release_date) return -1
    return b.first_release_date.localeCompare(a.first_release_date)
  }

  const grouped: Record<string, ReleaseGroupResult[]> = {}
  for (const album of albums) {
    const g = getGroup(album)
    if (!grouped[g]) grouped[g] = []
    grouped[g].push(album)
  }
  for (const g of GROUP_ORDER) {
    if (grouped[g]) grouped[g].sort(sortByDate)
  }

  function toggleExpand(albumMbid: string) {
    setExpandedMbid(prev => prev === albumMbid ? null : albumMbid)
  }

  return (
    <div style={styles.page}>
      <button style={styles.backBtn} onClick={() => navigate(-1)}>← Back</button>

      {isFetching && <div style={styles.loading}>Loading...</div>}
      {error && <div style={styles.error}>Failed to load artist.</div>}

      {data && (
        <>
          <div style={styles.header}>
            <ArtistImage url={data.image_thumb} size={120} />
            <div style={styles.headerText}>
              <h1 style={styles.heading}>{data.name}</h1>
              <div style={styles.meta}>
                {[data.type, data.country, data.begin && `Est. ${data.begin.slice(0, 4)}`]
                  .filter(Boolean).join(' · ')}
              </div>
              {data.disambiguation && (
                <div style={styles.disambiguation}>{data.disambiguation}</div>
              )}
            </div>
          </div>

          {albums.length === 0 && !isFetching && (
            <div style={styles.empty}>No releases found.</div>
          )}

          {GROUP_ORDER.filter(g => grouped[g]?.length > 0).map(groupName => (
            <div key={groupName} style={styles.group}>
              <div style={styles.sectionLabel}>
                {groupName} <span style={styles.sectionCount}>({grouped[groupName].length})</span>
              </div>
              <div style={styles.list}>
                {grouped[groupName].map((album, i) => {
                  const secondaryLabel = album.secondary_types.filter(Boolean).join(' · ')
                  const year = album.first_release_date?.slice(0, 4)
                  const jfItemId = libraryResult?.statuses[album.mbid ?? ''] ?? null
                  const inLibrary = !!jfItemId
                  const jellyfinLink = jfItemId && libraryResult?.jellyfin_url ? jellyfinWebUrl(libraryResult.jellyfin_url, jfItemId) : null
                  const initialState = inLibrary ? 'done' as RequestState : statusToRequestState(statusData?.[album.mbid ?? ''])
                  const isExpanded = expandedMbid === album.mbid
                  return (
                    <div key={album.mbid ?? i} style={isExpanded ? { ...styles.row, ...styles.rowExpanded } : styles.row}>
                      <div style={styles.rowHeader}>
                        {album.mbid && <CoverArt mbid={album.mbid} size={44} />}
                        <div style={styles.rowLeft}>
                          <span style={styles.rowTitle}>{album.title}</span>
                          <div style={styles.rowBottom}>
                            {year && <span style={styles.rowYear}>{year}</span>}
                            {secondaryLabel && <span style={styles.typeBadge}>{secondaryLabel}</span>}
                            {inLibrary && <span style={styles.libraryBadge}>In Library</span>}
                          </div>
                        </div>
                        <div style={styles.rowActions}>
                          {inLibrary
                            ? <>
                                <span style={styles.inLibraryTag}>In Library</span>
                                {jellyfinLink && <a href={jellyfinLink} target="_blank" rel="noopener noreferrer" style={styles.jellyfinLink}>Jellyfin ↗</a>}
                              </>
                            : <RequestButton
                                onRequest={async () => { await requestCollection(album) }}
                                initialState={initialState}
                              />
                          }
                          <button
                            style={isExpanded ? { ...styles.viewBtn, ...styles.viewBtnActive } : styles.viewBtn}
                            onClick={() => album.mbid && toggleExpand(album.mbid)}
                          >
                            {isExpanded ? 'Hide' : 'Tracks'}
                          </button>
                        </div>
                      </div>
                      {isExpanded && album.mbid && <TrackList mbid={album.mbid} />}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    maxWidth: 800,
    margin: '0 auto',
    padding: '2rem 1rem',
  },
  backBtn: {
    background: 'none',
    border: 'none',
    color: '#666',
    fontSize: '0.875rem',
    cursor: 'pointer',
    padding: '0 0 1.5rem 0',
    display: 'block',
  },
  loading: { color: '#555', padding: '2rem 0' },
  error: { color: '#ef4444', padding: '1rem', background: '#1a1a1a', borderRadius: 8 },
  header: { marginBottom: '2rem', display: 'flex', alignItems: 'center', gap: '1.25rem' },
  headerText: { flex: 1, minWidth: 0 },
  heading: {
    fontSize: '2rem',
    fontWeight: 700,
    color: '#f0f0f0',
    margin: '0 0 0.4rem 0',
  },
  meta: { fontSize: '0.875rem', color: '#777' },
  disambiguation: { fontSize: '0.825rem', color: '#555', marginTop: '0.25rem' },
  group: { marginBottom: '2rem' },
  sectionLabel: {
    fontSize: '0.775rem',
    color: '#555',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    fontWeight: 600,
    marginBottom: '0.75rem',
  },
  sectionCount: { fontWeight: 400, opacity: 0.6 },
  list: { display: 'flex', flexDirection: 'column', gap: '0.4rem' },
  row: {
    background: '#1a1a1a',
    border: '1px solid #2a2a2a',
    borderRadius: 8,
    overflow: 'hidden',
  },
  rowExpanded: {
    border: '1px solid #2563eb33',
  },
  rowHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0.75rem 1rem',
    gap: '1rem',
  },
  rowLeft: { display: 'flex', flexDirection: 'column', gap: '0.25rem', minWidth: 0, flex: 1, alignItems: 'flex-start' },
  rowTitle: {
    fontWeight: 500,
    fontSize: '0.95rem',
    color: '#f0f0f0',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  rowBottom: { display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' },
  rowYear: { fontSize: '0.775rem', color: '#666' },
  typeBadge: {
    fontSize: '0.65rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: '#888',
    background: '#252525',
    border: '1px solid #333',
    borderRadius: 4,
    padding: '0.1rem 0.4rem',
    lineHeight: 1.5,
  },
  rowActions: { display: 'flex', alignItems: 'center', gap: '0.4rem', flexShrink: 0 },
  requestBtn: {
    padding: '0.35rem 0.75rem',
    borderRadius: 6,
    border: '1px solid #2563eb',
    background: 'transparent',
    color: '#2563eb',
    fontSize: '0.825rem',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  viewBtn: {
    padding: '0.35rem 0.75rem',
    borderRadius: 6,
    border: '1px solid #333',
    background: 'transparent',
    color: '#aaa',
    fontSize: '0.825rem',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  viewBtnActive: {
    border: '1px solid #2563eb44',
    color: '#60a5fa',
  },
  requestedTag: {
    padding: '0.35rem 0.75rem',
    borderRadius: 6,
    background: '#14532d',
    color: '#86efac',
    fontSize: '0.825rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  duplicateTag: {
    padding: '0.35rem 0.75rem',
    borderRadius: 6,
    background: '#292524',
    color: '#a8a29e',
    fontSize: '0.825rem',
    whiteSpace: 'nowrap',
  },
  errorTag: {
    padding: '0.35rem 0.75rem',
    borderRadius: 6,
    background: '#450a0a',
    color: '#fca5a5',
    fontSize: '0.825rem',
    whiteSpace: 'nowrap',
  },
  trackList: {
    borderTop: '1px solid #222',
    padding: '0.5rem 1rem 0.75rem',
  },
  trackLoading: { color: '#555', fontSize: '0.825rem', padding: '0.75rem 0' },
  trackError: { color: '#ef4444', fontSize: '0.825rem', padding: '0.75rem 0' },
  trackEmpty: { color: '#555', fontSize: '0.825rem', padding: '0.75rem 0', textAlign: 'center' },
  discLabel: {
    fontSize: '0.7rem',
    color: '#555',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    fontWeight: 600,
    padding: '0.5rem 0 0.3rem',
  },
  trackRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.35rem 0',
    borderBottom: '1px solid #1e1e1e',
  },
  trackNum: {
    fontSize: '0.75rem',
    color: '#555',
    minWidth: 20,
    textAlign: 'right',
    flexShrink: 0,
  },
  trackTitle: {
    flex: 1,
    fontSize: '0.875rem',
    color: '#d0d0d0',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  trackDuration: {
    fontSize: '0.75rem',
    color: '#555',
    flexShrink: 0,
    minWidth: 36,
    textAlign: 'right',
  },
  inLibraryTag: {
    padding: '0.35rem 0.75rem',
    borderRadius: 6,
    background: '#052e16',
    color: '#4ade80',
    fontSize: '0.825rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  libraryBadge: {
    fontSize: '0.65rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: '#4ade80',
    background: '#052e16',
    border: '1px solid #166534',
    borderRadius: 4,
    padding: '0.1rem 0.4rem',
    lineHeight: 1.5,
  },
  jellyfinLink: {
    fontSize: '0.75rem', color: '#93c5fd', textDecoration: 'none', whiteSpace: 'nowrap',
  },
  empty: { color: '#555', textAlign: 'center', padding: '3rem 0' },
}
