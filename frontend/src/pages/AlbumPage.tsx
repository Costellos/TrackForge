import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getAlbumTracks, TrackResult } from '../api/search'
import { requestCollection, requestSong, checkMbidStatuses } from '../api/requests'
import { checkLibraryStatus, jellyfinWebUrl } from '../api/library'
import PreviewButton from '../components/PreviewButton'

function CoverArt({ mbid, size }: { mbid: string; size: number }) {
  const [failed, setFailed] = useState(false)
  const box: React.CSSProperties = { width: size, height: size, borderRadius: 6, flexShrink: 0, background: '#1e1e1e', border: '1px solid #2a2a2a' }
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

function AlbumRequestButton({ mbid, album, inLibrary, jellyfinLink }: { mbid: string; album: ReturnType<typeof getAlbumTracks> extends Promise<infer T> ? T : never; inLibrary?: boolean; jellyfinLink?: string | null }) {
  const [state, setState] = useState<RequestState>('idle')

  const { data: statusData } = useQuery({
    queryKey: ['request-statuses', [mbid]],
    queryFn: () => checkMbidStatuses([mbid]),
    enabled: !!mbid,
    staleTime: 1000 * 30,
  })

  useEffect(() => {
    const status = statusData?.[mbid]
    if (status) setState(statusToRequestState(status))
  }, [statusData, mbid])

  if (inLibrary) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <span style={styles.inLibraryTag}>In Library</span>
      {jellyfinLink && <a href={jellyfinLink} target="_blank" rel="noopener noreferrer" style={styles.jellyfinLink}>View on Jellyfin</a>}
    </div>
  )

  async function handle() {
    setState('loading')
    try {
      await requestCollection({
        mbid: album.release_group_mbid,
        title: album.album_title,
        type: album.album_type,
        secondary_types: album.album_secondary_types,
        first_release_date: album.first_release_date,
        artists: album.artists,
        score: null,
        track_count: null,
      })
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
    <button style={styles.requestAlbumBtn} onClick={handle} disabled={state === 'loading'}>
      {state === 'loading' ? '...' : 'Request Album'}
    </button>
  )
}

function TrackRequestButton({ track, artists, initialState = 'idle' }: {
  track: TrackResult
  artists: { mbid: string; name: string }[]
  initialState?: RequestState
}) {
  const [state, setState] = useState<RequestState>(initialState)

  useEffect(() => {
    if (initialState !== 'idle') setState(initialState)
  }, [initialState])

  if (!track.recording_mbid) {
    return <button style={styles.trackRequestBtn} disabled>Request</button>
  }

  async function handle() {
    setState('loading')
    try {
      const primary = artists[0]
      await requestSong({
        recording_mbid: track.recording_mbid!,
        title: track.title,
        artist_mbid: primary?.mbid ?? null,
        artist_name: primary?.name ?? null,
        length_ms: track.length_ms,
      })
      setState('done')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setState(status === 409 ? 'duplicate' : 'error')
    }
  }

  if (state === 'done') return <span style={styles.trackRequestedTag}>Requested</span>
  if (state === 'duplicate') return <span style={styles.trackDuplicateTag}>Requested</span>
  if (state === 'error') return <span style={styles.trackErrorTag}>Error</span>

  return (
    <button style={styles.trackRequestBtnActive} onClick={handle} disabled={state === 'loading'}>
      {state === 'loading' ? '...' : 'Request'}
    </button>
  )
}

export default function AlbumPage() {
  const { mbid } = useParams<{ mbid: string }>()
  const navigate = useNavigate()
  const [selectedRelease, setSelectedRelease] = useState<string | undefined>(undefined)

  const { data, isFetching, error } = useQuery({
    queryKey: ['album-tracks', mbid, selectedRelease],
    queryFn: () => getAlbumTracks(mbid!, selectedRelease),
    enabled: !!mbid,
    staleTime: 1000 * 60 * 5,
  })

  // Check library status using both release-group and release MBIDs
  const libraryCheckMbids = [mbid, data?.release_mbid].filter((m): m is string => !!m)

  const { data: libraryResult } = useQuery({
    queryKey: ['library-statuses', libraryCheckMbids],
    queryFn: () => checkLibraryStatus(libraryCheckMbids),
    enabled: libraryCheckMbids.length > 0,
    staleTime: 1000 * 60 * 5,
  })

  const trackMbids = data?.tracks.map(t => t.recording_mbid).filter((m): m is string => !!m) ?? []

  const { data: trackStatusData } = useQuery({
    queryKey: ['request-statuses', trackMbids],
    queryFn: () => checkMbidStatuses(trackMbids),
    enabled: trackMbids.length > 0,
    staleTime: 1000 * 30,
  })

  const libraryStatuses = libraryResult?.statuses
  const inLibrary = libraryCheckMbids.some(m => !!libraryStatuses?.[m])
  const jellyfinItemId = libraryCheckMbids.map(m => libraryStatuses?.[m]).find(id => !!id) ?? null
  const jellyfinLink = jellyfinItemId && libraryResult?.jellyfin_url
    ? jellyfinWebUrl(libraryResult.jellyfin_url, jellyfinItemId)
    : null
  const year = data?.first_release_date?.slice(0, 4)
  const typeLabel = [data?.album_type, ...(data?.album_secondary_types ?? [])].filter(Boolean).join(' · ')
  const totalDuration = data?.tracks.reduce((sum, t) => sum + (t.length_ms ?? 0), 0) ?? 0

  // Group tracks by disc
  const discs = data?.tracks.reduce<Record<number, typeof data.tracks>>((acc, t) => {
    const d = t.disc ?? 1
    if (!acc[d]) acc[d] = []
    acc[d].push(t)
    return acc
  }, {}) ?? {}
  const discNumbers = Object.keys(discs).map(Number).sort()
  const multiDisc = discNumbers.length > 1

  return (
    <div style={styles.page}>
      <button style={styles.backBtn} onClick={() => navigate(-1)}>← Back</button>

      {isFetching && <div style={styles.loading}>Loading...</div>}
      {error && <div style={styles.error}>Failed to load album.</div>}

      {data && (
        <>
          <div style={styles.header}>
            <CoverArt mbid={data.release_group_mbid} size={160} />
            <div style={styles.headerLeft}>
              <h1 style={styles.heading}>{data.album_title}</h1>
              <div style={styles.artistName}>
                {data.artists.map((a, i) => (
                  <span key={a.mbid ?? i}>
                    {i > 0 && ', '}
                    <span
                      style={styles.artistLink}
                      onClick={(e) => { e.stopPropagation(); if (a.mbid) navigate(`/artist/${a.mbid}`) }}
                    >
                      {a.name}
                    </span>
                  </span>
                ))}
              </div>
              <div style={styles.meta}>
                {[typeLabel, year, data.tracks.length > 0 ? `${data.tracks.length} tracks` : null, totalDuration > 0 ? formatDuration(totalDuration) : null].filter(Boolean).join(' · ')}
                {inLibrary && (
                  jellyfinLink
                    ? <a href={jellyfinLink} target="_blank" rel="noopener noreferrer" style={{ ...styles.inLibraryBadge, textDecoration: 'none' }}>In Library ↗</a>
                    : <span style={styles.inLibraryBadge}>In Library</span>
                )}
              </div>
            </div>
            <AlbumRequestButton mbid={mbid!} album={data} inLibrary={inLibrary} jellyfinLink={jellyfinLink} />
          </div>

          {data.releases && data.releases.length > 1 && (
            <div style={styles.releasePicker}>
              <label style={styles.releaseLabel}>Release:</label>
              <select
                style={styles.releaseSelect}
                value={data.release_mbid ?? ''}
                onChange={e => setSelectedRelease(e.target.value || undefined)}
              >
                {data.releases.map(r => (
                  <option key={r.mbid} value={r.mbid}>{r.label}</option>
                ))}
              </select>
            </div>
          )}

          <div style={styles.trackList}>
            {discNumbers.map(disc => (
              <div key={disc}>
                {multiDisc && (
                  <div style={styles.discLabel}>Disc {disc}</div>
                )}
                {discs[disc].map((track, i) => {
                  const trackState = track.recording_mbid ? statusToRequestState(trackStatusData?.[track.recording_mbid]) : 'idle'
                  const artistName = data.artists.map(a => a.name).join(', ')
                  return (
                    <div key={i} style={styles.trackRow}>
                      <span style={styles.trackNum}>{track.number ?? track.position}</span>
                      <PreviewButton recordingMbid={track.recording_mbid} title={track.title} artist={artistName} />
                      <span style={styles.trackTitle}>{track.title}</span>
                      <span style={styles.trackDuration}>{formatDuration(track.length_ms)}</span>
                      <TrackRequestButton track={track} artists={data.artists} initialState={trackState} />
                    </div>
                  )
                })}
              </div>
            ))}

            {data.tracks.length === 0 && (
              <div style={styles.empty}>No track information available.</div>
            )}
          </div>
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
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: '1.5rem',
    marginBottom: '2rem',
  },
  headerLeft: { display: 'flex', flexDirection: 'column', gap: '0.3rem', flex: 1, minWidth: 0 },
  heading: {
    fontSize: '1.75rem',
    fontWeight: 700,
    color: '#f0f0f0',
    margin: 0,
  },
  artistName: { fontSize: '1rem', color: '#aaa' },
  artistLink: { cursor: 'pointer', color: '#93c5fd', textDecoration: 'none' },
  meta: { fontSize: '0.825rem', color: '#666', display: 'flex', alignItems: 'center', gap: '0.5rem' },
  inLibraryTag: {
    padding: '0.5rem 1.25rem',
    borderRadius: 6,
    background: '#052e16',
    color: '#4ade80',
    fontSize: '0.875rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  inLibraryBadge: {
    padding: '0.1rem 0.4rem',
    borderRadius: 3,
    fontSize: '0.65rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.03em',
    color: '#4ade80',
    background: '#052e16',
    whiteSpace: 'nowrap',
  },
  requestAlbumBtn: {
    padding: '0.5rem 1.25rem',
    borderRadius: 6,
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    fontSize: '0.875rem',
    cursor: 'pointer',
    fontWeight: 500,
    whiteSpace: 'nowrap',
    flexShrink: 0,
  },
  requestedTag: {
    padding: '0.5rem 1.25rem',
    borderRadius: 6,
    background: '#14532d',
    color: '#86efac',
    fontSize: '0.875rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  duplicateTag: {
    padding: '0.5rem 1.25rem',
    borderRadius: 6,
    background: '#292524',
    color: '#a8a29e',
    fontSize: '0.875rem',
    whiteSpace: 'nowrap',
  },
  errorTag: {
    padding: '0.5rem 1.25rem',
    borderRadius: 6,
    background: '#450a0a',
    color: '#fca5a5',
    fontSize: '0.875rem',
    whiteSpace: 'nowrap',
  },
  discLabel: {
    fontSize: '0.75rem',
    color: '#555',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    fontWeight: 600,
    padding: '0.75rem 0 0.4rem',
  },
  trackList: {
    display: 'flex',
    flexDirection: 'column',
  },
  trackRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.5rem 0.5rem',
    borderBottom: '1px solid #1e1e1e',
  },
  trackNum: {
    fontSize: '0.775rem',
    color: '#555',
    minWidth: 24,
    textAlign: 'right',
    flexShrink: 0,
  },
  trackTitle: {
    flex: 1,
    fontSize: '0.9rem',
    color: '#e0e0e0',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  trackDuration: {
    fontSize: '0.775rem',
    color: '#555',
    flexShrink: 0,
    minWidth: 36,
    textAlign: 'right',
  },
  trackRequestBtn: {
    padding: '0.2rem 0.6rem',
    borderRadius: 5,
    border: '1px solid #2a2a2a',
    background: 'transparent',
    color: '#333',
    fontSize: '0.75rem',
    cursor: 'not-allowed',
    flexShrink: 0,
  },
  trackRequestBtnActive: {
    padding: '0.2rem 0.6rem',
    borderRadius: 5,
    border: '1px solid #2563eb',
    background: 'transparent',
    color: '#2563eb',
    fontSize: '0.75rem',
    cursor: 'pointer',
    flexShrink: 0,
  },
  trackRequestedTag: {
    padding: '0.2rem 0.6rem',
    borderRadius: 5,
    background: '#14532d',
    color: '#86efac',
    fontSize: '0.75rem',
    fontWeight: 500,
    flexShrink: 0,
  },
  trackDuplicateTag: {
    padding: '0.2rem 0.6rem',
    borderRadius: 5,
    background: '#292524',
    color: '#a8a29e',
    fontSize: '0.75rem',
    fontWeight: 500,
    flexShrink: 0,
  },
  trackErrorTag: {
    padding: '0.2rem 0.6rem',
    borderRadius: 5,
    background: '#450a0a',
    color: '#fca5a5',
    fontSize: '0.75rem',
    flexShrink: 0,
  },
  jellyfinLink: {
    fontSize: '0.75rem',
    color: '#93c5fd',
    textDecoration: 'none',
    whiteSpace: 'nowrap',
  },
  releasePicker: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    marginBottom: '1rem',
    padding: '0.5rem 0',
  },
  releaseLabel: {
    fontSize: '0.8rem',
    color: '#888',
    flexShrink: 0,
  },
  releaseSelect: {
    flex: 1,
    maxWidth: 500,
    padding: '0.35rem 0.5rem',
    borderRadius: 5,
    border: '1px solid #333',
    background: '#1a1a1a',
    color: '#e0e0e0',
    fontSize: '0.8rem',
    cursor: 'pointer',
  },
  empty: { color: '#555', padding: '2rem 0', textAlign: 'center' },
}
