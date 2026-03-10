import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { search, SearchType, ArtistResult, ReleaseGroupResult, RecordingResult, getArtistImages } from '../api/search'
import { requestCollection, checkMbidStatuses } from '../api/requests'
import { checkLibraryStatus } from '../api/library'

function formatDuration(ms: number | null): string {
  if (!ms) return ''
  const total = Math.round(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
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

type RequestState = 'idle' | 'loading' | 'done' | 'duplicate' | 'error'

function statusToRequestState(status: string | null | undefined): RequestState {
  if (!status) return 'idle'
  if (status === 'available') return 'done'
  return 'duplicate'
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

function ArtistThumb({ mbid, size }: { mbid: string | null; size: number }) {
  const { data } = useQuery({
    queryKey: ['artist-images', mbid],
    queryFn: () => getArtistImages(mbid!),
    enabled: !!mbid,
    staleTime: 1000 * 60 * 60,
  })
  const [failed, setFailed] = useState(false)
  const box: React.CSSProperties = { width: size, height: size, borderRadius: '50%', flexShrink: 0, background: '#1e1e1e', border: '1px solid #2a2a2a' }
  const url = data?.thumb
  if (!url || failed) return <div style={box} />
  return <img src={url} alt="" onError={() => setFailed(true)} style={{ ...box, objectFit: 'cover', border: 'none' }} />
}

function ArtistCard({ artist }: { artist: ArtistResult }) {
  const navigate = useNavigate()
  const meta = [artist.type, artist.country, artist.begin && `Est. ${artist.begin.slice(0, 4)}`].filter(Boolean)
  return (
    <div style={styles.card}>
      <ArtistThumb mbid={artist.mbid} size={48} />
      <div style={styles.cardMain}>
        <div style={styles.cardTitle}>{artist.name}</div>
        <div style={styles.cardBottom}>
          {meta.map((m, i) => <span key={i} style={styles.cardMetaItem}>{m}</span>)}
          {artist.disambiguation && <span style={styles.typeBadge}>{artist.disambiguation}</span>}
        </div>
      </div>
      <button style={styles.viewBtn} onClick={() => navigate(`/artist/${artist.mbid}`)}>
        View
      </button>
    </div>
  )
}

function AlbumCard({ album, initialState, inLibrary }: { album: ReleaseGroupResult; initialState?: RequestState; inLibrary?: boolean }) {
  const navigate = useNavigate()
  const artistNames = album.artists.map(a => a.name).join(', ')
  const year = album.first_release_date?.slice(0, 4)
  const secondaryLabel = album.secondary_types.filter(Boolean).join(' · ')

  return (
    <div style={styles.card}>
      {album.mbid && <CoverArt mbid={album.mbid} size={48} />}
      <div style={styles.cardMain}>
        <div style={styles.cardTitle}>{album.title}</div>
        <div style={styles.cardBottom}>
          {artistNames && <span style={styles.cardMetaItem}>{artistNames}</span>}
          {year && <span style={styles.cardMetaItem}>{year}</span>}
          {secondaryLabel && <span style={styles.typeBadge}>{secondaryLabel}</span>}
          {inLibrary && <span style={styles.libraryBadge}>In Library</span>}
        </div>
      </div>
      <div style={styles.cardActions}>
        {inLibrary
          ? <span style={styles.inLibraryTag}>In Library</span>
          : <RequestButton onRequest={async () => { await requestCollection(album) }} initialState={initialState} />
        }
        <button style={styles.viewBtn} onClick={() => navigate(`/album/${album.mbid}`)}>
          View
        </button>
      </div>
    </div>
  )
}

function SongCard({ recording }: { recording: RecordingResult }) {
  const artistNames = recording.artists.map(a => a.name).join(', ')
  const firstRelease = recording.releases[0]
  const duration = formatDuration(recording.length_ms)

  return (
    <div style={styles.card}>
      <div style={styles.cardMain}>
        <div style={styles.cardTitle}>{recording.title}</div>
        <div style={styles.cardBottom}>
          {artistNames && <span style={styles.cardMetaItem}>{artistNames}</span>}
          {firstRelease?.title && <span style={styles.cardMetaItem}>{firstRelease.title}</span>}
          {firstRelease?.date && <span style={styles.cardMetaItem}>{firstRelease.date.slice(0, 4)}</span>}
          {duration && <span style={styles.typeBadge}>{duration}</span>}
        </div>
      </div>
      <button style={{ ...styles.requestBtn, opacity: 0.4 }} disabled>Request</button>
    </div>
  )
}

export default function Search() {
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const [type, setType] = useState<SearchType>('artist')

  const { data, isFetching, error } = useQuery({
    queryKey: ['search', query, type],
    queryFn: () => search(query, type),
    enabled: query.length > 0,
    staleTime: 1000 * 60 * 5,
  })

  const mbids = type !== 'artist'
    ? (data?.results.map(r => (r as { mbid: string }).mbid).filter(Boolean) ?? [])
    : []

  const { data: statusData } = useQuery({
    queryKey: ['request-statuses', mbids],
    queryFn: () => checkMbidStatuses(mbids),
    enabled: mbids.length > 0,
    staleTime: 1000 * 30,
  })

  const { data: libraryData } = useQuery({
    queryKey: ['library-statuses', mbids],
    queryFn: () => checkLibraryStatus(mbids),
    enabled: mbids.length > 0,
    staleTime: 1000 * 60 * 5,
  })

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim()) setQuery(input.trim())
  }, [input])

  const placeholder =
    type === 'artist' ? 'Search for an artist...' :
    type === 'album'  ? 'Search for an album...' :
                        'Search for a song...'

  return (
    <div style={styles.page}>
      <h1 style={styles.heading}>Search</h1>

      <form onSubmit={handleSubmit} style={styles.form}>
        <div style={styles.typeSelector}>
          {(['artist', 'album', 'song'] as SearchType[]).map(t => (
            <button
              key={t}
              type="button"
              onClick={() => setType(t)}
              style={type === t ? { ...styles.typeBtn, ...styles.typeBtnActive } : styles.typeBtn}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        <div style={styles.inputRow}>
          <input
            style={styles.input}
            type="text"
            placeholder={placeholder}
            value={input}
            onChange={e => setInput(e.target.value)}
            autoFocus
          />
          <button type="submit" style={styles.searchBtn} disabled={isFetching}>
            {isFetching ? 'Searching...' : 'Search'}
          </button>
        </div>
      </form>

      {type === 'artist' && !query && (
        <div style={styles.hint}>Search for an artist to browse their discography and request albums.</div>
      )}

      {error && <div style={styles.error}>Search failed. Check that the API is running.</div>}

      {data && (
        <div style={styles.results}>
          <div style={styles.resultCount}>
            {data.results.length} result{data.results.length !== 1 ? 's' : ''} for "{data.query}"
          </div>
          {data.results.map((result, i) => {
            const mbid = (result as { mbid: string }).mbid
            const initialState = statusToRequestState(statusData?.[mbid])
            if (type === 'artist') return <ArtistCard key={i} artist={result as ArtistResult} />
            if (type === 'album') return <AlbumCard key={i} album={result as ReleaseGroupResult} initialState={initialState} inLibrary={libraryData?.[mbid] === true} />
            if (type === 'song') return <SongCard key={i} recording={result as RecordingResult} />
            return null
          })}
        </div>
      )}

      {data?.results.length === 0 && (
        <div style={styles.empty}>No results found for "{query}".</div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: { maxWidth: 800, margin: '0 auto', padding: '2rem 1rem' },
  heading: { fontSize: '1.75rem', fontWeight: 700, marginBottom: '1.5rem', color: '#f0f0f0' },
  form: { display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '2rem' },
  typeSelector: { display: 'flex', gap: '0.5rem' },
  typeBtn: {
    padding: '0.4rem 1rem', borderRadius: 6, border: '1px solid #333',
    background: '#1a1a1a', color: '#aaa', cursor: 'pointer', fontSize: '0.875rem',
  },
  typeBtnActive: { background: '#2563eb', border: '1px solid #2563eb', color: '#fff' },
  inputRow: { display: 'flex', gap: '0.5rem' },
  input: {
    flex: 1, padding: '0.6rem 0.875rem', borderRadius: 6, border: '1px solid #333',
    background: '#1a1a1a', color: '#f0f0f0', fontSize: '1rem', outline: 'none',
  },
  searchBtn: {
    padding: '0.6rem 1.25rem', borderRadius: 6, border: 'none',
    background: '#2563eb', color: '#fff', fontSize: '1rem', cursor: 'pointer',
  },
  hint: { color: '#555', fontSize: '0.875rem', marginBottom: '1rem' },
  results: { display: 'flex', flexDirection: 'column', gap: '0.5rem' },
  resultCount: { fontSize: '0.8rem', color: '#666', marginBottom: '0.5rem' },
  card: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0.75rem 1rem', background: '#1a1a1a', border: '1px solid #2a2a2a',
    borderRadius: 8, gap: '1rem',
  },
  cardMain: { display: 'flex', flexDirection: 'column', gap: '0.25rem', minWidth: 0, flex: 1, alignItems: 'flex-start' },
  cardTitle: {
    fontWeight: 500, fontSize: '0.95rem', color: '#f0f0f0',
    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', width: '100%',
  },
  cardBottom: { display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' },
  cardMetaItem: { fontSize: '0.775rem', color: '#666' },
  typeBadge: {
    fontSize: '0.65rem', fontWeight: 600, textTransform: 'uppercase',
    letterSpacing: '0.05em', color: '#888', background: '#252525',
    border: '1px solid #333', borderRadius: 4, padding: '0.1rem 0.4rem', lineHeight: 1.5,
  },
  cardActions: { display: 'flex', alignItems: 'center', gap: '0.4rem', flexShrink: 0 },
  viewBtn: {
    padding: '0.4rem 0.875rem', borderRadius: 6, border: '1px solid #333',
    background: 'transparent', color: '#aaa', fontSize: '0.825rem',
    cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0,
  },
  requestBtn: {
    padding: '0.4rem 0.875rem', borderRadius: 6, border: '1px solid #2563eb',
    background: 'transparent', color: '#2563eb', fontSize: '0.825rem',
    cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0,
  },
  requestedTag: {
    padding: '0.4rem 0.875rem', borderRadius: 6, background: '#14532d',
    color: '#86efac', fontSize: '0.825rem', fontWeight: 500, whiteSpace: 'nowrap', flexShrink: 0,
  },
  duplicateTag: {
    padding: '0.4rem 0.875rem', borderRadius: 6, background: '#292524',
    color: '#a8a29e', fontSize: '0.825rem', fontWeight: 500, whiteSpace: 'nowrap', flexShrink: 0,
  },
  errorTag: {
    padding: '0.4rem 0.875rem', borderRadius: 6, background: '#450a0a',
    color: '#fca5a5', fontSize: '0.825rem', whiteSpace: 'nowrap', flexShrink: 0,
  },
  inLibraryTag: {
    padding: '0.4rem 0.875rem', borderRadius: 6, background: '#052e16',
    color: '#4ade80', fontSize: '0.825rem', fontWeight: 500, whiteSpace: 'nowrap', flexShrink: 0,
  },
  libraryBadge: {
    fontSize: '0.65rem', fontWeight: 600, textTransform: 'uppercase',
    letterSpacing: '0.05em', color: '#4ade80', background: '#052e16',
    border: '1px solid #166534', borderRadius: 4, padding: '0.1rem 0.4rem', lineHeight: 1.5,
  },
  error: { color: '#ef4444', padding: '1rem', background: '#1a1a1a', borderRadius: 8 },
  empty: { color: '#666', textAlign: 'center', padding: '2rem' },
}
