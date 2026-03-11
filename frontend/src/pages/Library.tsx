import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listLibrary, LibraryEntry, listCandidates, selectCandidate, retryRequest, NzbCandidate } from '../api/requests'
import { jellyfinWebUrl } from '../api/library'
import { useAuthStore } from '../stores/auth'

const STATUS_CONFIG: Record<string, { label: string; style: React.CSSProperties }> = {
  pending_approval: { label: 'Pending', style: { background: '#422006', color: '#fdba74' } },
  approved:         { label: 'Approved', style: { background: '#1e3a5f', color: '#93c5fd' } },
  searching:        { label: 'Searching', style: { background: '#1e3a5f', color: '#93c5fd' } },
  downloading:      { label: 'Downloading', style: { background: '#1e3a5f', color: '#93c5fd' } },
  processing:       { label: 'Processing', style: { background: '#1e3a5f', color: '#93c5fd' } },
  available:        { label: 'Available', style: { background: '#14532d', color: '#86efac' } },
  failed:           { label: 'Failed', style: { background: '#450a0a', color: '#fca5a5' } },
  cancelled:        { label: 'Cancelled', style: { background: '#1c1917', color: '#78716c' } },
}

type Section = 'requested' | 'downloading' | 'processing' | 'failed' | 'jellyfin'

const SECTION_CONFIG: Record<Section, { label: string; color: string; emptyMsg: string }> = {
  requested:   { label: 'Requested', color: '#fdba74', emptyMsg: 'No pending requests.' },
  downloading: { label: 'Downloading', color: '#93c5fd', emptyMsg: 'Nothing downloading right now.' },
  processing:  { label: 'Processing', color: '#93c5fd', emptyMsg: 'Nothing being processed.' },
  failed:      { label: 'Failed', color: '#fca5a5', emptyMsg: 'No failed requests.' },
  jellyfin:    { label: 'In Jellyfin', color: '#4ade80', emptyMsg: 'No items in Jellyfin yet.' },
}

function classifyEntry(entry: LibraryEntry): Section {
  if (entry.jellyfin_item_id) return 'jellyfin'
  switch (entry.status) {
    case 'pending_approval':
    case 'approved':
    case 'searching':
      return 'requested'
    case 'downloading':
      return 'downloading'
    case 'processing':
    case 'available':
      return 'processing'
    case 'failed':
      return 'failed'
    default:
      return 'requested'
  }
}

function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? { label: status, style: { background: '#222', color: '#aaa' } }
  return <span style={{ ...styles.badge, ...config.style }}>{config.label}</span>
}

function CoverArt({ url, size }: { url: string | null; size: number }) {
  const [failed, setFailed] = useState(false)
  const box: React.CSSProperties = {
    width: size, height: size, borderRadius: 4, flexShrink: 0,
    background: '#1e1e1e', border: '1px solid #2a2a2a',
  }
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

function formatSize(bytes: number): string {
  if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + ' GB'
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(0) + ' MB'
  return (bytes / 1024).toFixed(0) + ' KB'
}

function formatScore(score: number): string {
  return score.toFixed(1)
}

function CandidatesModal({ requestId, entryName, entrySubtitle, onClose }: { requestId: string; entryName: string; entrySubtitle: string | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [submitting, setSubmitting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [artistOverride, setArtistOverride] = useState('')
  const [appliedOverride, setAppliedOverride] = useState<string | undefined>(undefined)

  const { data: candidates, isLoading } = useQuery({
    queryKey: ['candidates', requestId, appliedOverride],
    queryFn: () => listCandidates(requestId, appliedOverride),
  })

  // Extract artist from subtitle (format is "Album · Artist Name" or just "Artist Name")
  const detectedArtist = entrySubtitle?.split(' · ').slice(1).join(' · ') || null

  async function handleSelect(c: NzbCandidate) {
    setSubmitting(c.download_url)
    setError(null)
    try {
      await selectCandidate(requestId, c.download_url, c.title)
      queryClient.invalidateQueries({ queryKey: ['library'] })
      onClose()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to submit NZB')
    } finally {
      setSubmitting(null)
    }
  }

  async function handleAutoRetry() {
    setSubmitting('auto')
    setError(null)
    try {
      await retryRequest(requestId)
      queryClient.invalidateQueries({ queryKey: ['library'] })
      onClose()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to retry')
    } finally {
      setSubmitting(null)
    }
  }

  return (
    <div style={modalStyles.overlay} onClick={onClose}>
      <div style={modalStyles.modal} onClick={e => e.stopPropagation()}>
        <div style={modalStyles.header}>
          <h3 style={modalStyles.title}>NZBs for {entryName}</h3>
          <button style={modalStyles.closeBtn} onClick={onClose}>×</button>
        </div>

        <div style={modalStyles.actions}>
          <button
            style={modalStyles.autoBtn}
            onClick={handleAutoRetry}
            disabled={submitting !== null}
          >
            {submitting === 'auto' ? 'Retrying...' : 'Auto-Retry (next best)'}
          </button>
        </div>

        <div style={modalStyles.artistRow}>
          <span style={modalStyles.artistLabel}>
            Artist: {detectedArtist ? <span style={{ color: '#e0e0e0' }}>{detectedArtist}</span> : <span style={{ color: '#ef4444' }}>Not found</span>}
          </span>
          <div style={modalStyles.artistInputRow}>
            <input
              type="text"
              placeholder="Override artist name..."
              value={artistOverride}
              onChange={e => setArtistOverride(e.target.value)}
              style={modalStyles.artistInput}
            />
            <button
              style={modalStyles.artistSearchBtn}
              disabled={!artistOverride.trim() || isLoading}
              onClick={() => { setAppliedOverride(artistOverride.trim()); }}
            >
              Search
            </button>
            {appliedOverride && (
              <button
                style={modalStyles.artistClearBtn}
                onClick={() => { setArtistOverride(''); setAppliedOverride(undefined); }}
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {error && <div style={modalStyles.error}>{error}</div>}

        {isLoading && <div style={modalStyles.empty}>Searching indexers...</div>}

        {candidates && candidates.length === 0 && (
          <div style={modalStyles.empty}>No results found from indexers.</div>
        )}

        <div style={modalStyles.list}>
          {candidates?.map((c, i) => (
            <div
              key={i}
              style={{
                ...modalStyles.candidate,
                opacity: c.already_tried ? 0.5 : 1,
              }}
            >
              <div style={modalStyles.candidateInfo}>
                <div style={modalStyles.candidateTitle}>{c.title}</div>
                <div style={modalStyles.candidateMeta}>
                  {c.indexer} · {formatSize(c.size)} · {Math.round(c.age_days)}d old · {c.grabs} grabs · Score: {formatScore(c.score)}
                  {c.format_score >= 3 && <span style={modalStyles.flacTag}>FLAC</span>}
                  {c.already_tried && <span style={modalStyles.triedTag}>Already tried</span>}
                </div>
              </div>
              <button
                style={modalStyles.selectBtn}
                onClick={() => handleSelect(c)}
                disabled={submitting !== null}
              >
                {submitting === c.download_url ? 'Sending...' : 'Select'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function EntryCard({ entry, isAdmin, jellyfinUrl, section }: { entry: LibraryEntry; isAdmin: boolean; jellyfinUrl?: string | null; section: Section }) {
  const navigate = useNavigate()
  const [showCandidates, setShowCandidates] = useState(false)
  const typeLabel = entry.target_type === 'artist' ? 'Artist' : entry.target_type === 'song' ? 'Song' : 'Album'
  const meta = [entry.subtitle, entry.year].filter(Boolean).join(' · ')
  const isCollection = entry.target_type === 'collection'

  function handleClick() {
    if (entry.mbid) {
      navigate(isCollection ? `/album/${entry.mbid}` : `/artist/${entry.mbid}`)
    }
  }

  return (
    <>
      <div style={styles.card} onClick={handleClick}>
        {isCollection && <CoverArt url={entry.mbid ? `https://coverartarchive.org/release-group/${entry.mbid}/front-250` : null} size={44} />}
        <div style={styles.cardLeft}>
          <span style={styles.typeTag}>{typeLabel}</span>
          <div style={styles.cardTitle}>{entry.name}</div>
          {meta && <div style={styles.cardMeta}>{meta}</div>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {entry.status === 'failed' && isAdmin && (
            <button
              style={styles.nzbBtn}
              onClick={e => { e.stopPropagation(); setShowCandidates(true) }}
            >
              Browse NZBs
            </button>
          )}
          {section === 'jellyfin' && entry.jellyfin_item_id && jellyfinUrl ? (
            <a
              href={jellyfinWebUrl(jellyfinUrl, entry.jellyfin_item_id)}
              target="_blank"
              rel="noopener noreferrer"
              style={{ ...styles.badge, background: '#052e16', color: '#4ade80', textDecoration: 'none' }}
              onClick={e => e.stopPropagation()}
            >
              Jellyfin ↗
            </a>
          ) : (
            <StatusBadge status={entry.status} />
          )}
        </div>
      </div>
      {showCandidates && (
        <CandidatesModal requestId={entry.id} entryName={entry.name} entrySubtitle={entry.subtitle} onClose={() => setShowCandidates(false)} />
      )}
    </>
  )
}

export default function Library() {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'admin' || user?.role === 'moderator'

  const { data: libraryData, isFetching, error } = useQuery({
    queryKey: ['library'],
    queryFn: listLibrary,
    staleTime: 1000 * 30,
  })

  const entries = libraryData?.entries ?? []
  const jellyfinUrl = libraryData?.jellyfin_url ?? null

  // Group into sections
  const sections: Record<Section, LibraryEntry[]> = {
    requested: [],
    downloading: [],
    processing: [],
    failed: [],
    jellyfin: [],
  }
  for (const entry of entries) {
    sections[classifyEntry(entry)].push(entry)
  }

  const totalCount = entries.length
  const sectionOrder: Section[] = ['requested', 'downloading', 'processing', 'failed', 'jellyfin']
  const nonEmptySections = sectionOrder.filter(s => sections[s].length > 0)

  return (
    <div style={styles.page}>
      <h1 style={styles.heading}>Library</h1>

      {error && (
        <div style={styles.error}>Failed to load library. Check that the API is running.</div>
      )}

      {isFetching && !libraryData && (
        <div style={styles.empty}>Loading...</div>
      )}

      {!isFetching && totalCount === 0 && (
        <div style={styles.empty}>Nothing here yet. Use Search to request albums.</div>
      )}

      {nonEmptySections.map(section => {
        const config = SECTION_CONFIG[section]
        const items = sections[section]
        return (
          <div key={section} style={styles.section}>
            <div style={styles.sectionDivider}>
              <span style={{ ...styles.sectionLabel, color: config.color }}>{config.label}</span>
              <span style={styles.sectionCount}>{items.length}</span>
            </div>
            <div style={styles.list}>
              {items.map(entry => (
                <EntryCard key={entry.id} entry={entry} isAdmin={isAdmin} jellyfinUrl={jellyfinUrl} section={section} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    maxWidth: 800,
    margin: '0 auto',
    padding: '2rem 1rem',
  },
  heading: {
    fontSize: '1.75rem',
    fontWeight: 700,
    marginBottom: '1.5rem',
    color: '#f0f0f0',
  },
  section: {
    marginBottom: '1.5rem',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  card: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0.875rem 1rem',
    background: '#1a1a1a',
    border: '1px solid #2a2a2a',
    borderRadius: 8,
    gap: '1rem',
    cursor: 'pointer',
  },
  cardLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.2rem',
    minWidth: 0,
    flex: 1,
  },
  typeTag: {
    fontSize: '0.7rem',
    color: '#555',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    fontWeight: 600,
  },
  cardTitle: {
    fontWeight: 600,
    fontSize: '0.95rem',
    color: '#f0f0f0',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  cardMeta: {
    fontSize: '0.75rem',
    color: '#666',
  },
  badge: {
    padding: '0.3rem 0.75rem',
    borderRadius: 5,
    fontSize: '0.775rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
    flexShrink: 0,
  },
  sectionDivider: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '1.25rem 0 0.5rem',
    borderTop: '1px solid #2a2a2a',
    marginTop: '0.75rem',
  },
  sectionLabel: {
    fontSize: '0.8rem',
    fontWeight: 600,
    color: '#4ade80',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  sectionCount: {
    fontSize: '0.75rem',
    color: '#555',
  },
  error: {
    color: '#ef4444',
    padding: '1rem',
    background: '#1a1a1a',
    borderRadius: 8,
    marginBottom: '1rem',
  },
  empty: {
    color: '#555',
    textAlign: 'center',
    padding: '3rem 1rem',
  },
  nzbBtn: {
    padding: '0.3rem 0.65rem',
    borderRadius: 5,
    border: '1px solid #d97706',
    background: '#422006',
    color: '#fbbf24',
    cursor: 'pointer',
    fontSize: '0.75rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
}

const modalStyles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  },
  modal: {
    background: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: 12,
    width: '90vw',
    maxWidth: 700,
    maxHeight: '80vh',
    display: 'flex',
    flexDirection: 'column',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '1rem 1.25rem',
    borderBottom: '1px solid #2a2a2a',
  },
  title: {
    margin: 0,
    fontSize: '1.1rem',
    fontWeight: 600,
    color: '#f0f0f0',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#888',
    fontSize: '1.5rem',
    cursor: 'pointer',
    padding: '0 0.25rem',
  },
  actions: {
    padding: '0.75rem 1.25rem',
    borderBottom: '1px solid #2a2a2a',
  },
  autoBtn: {
    padding: '0.4rem 1rem',
    borderRadius: 6,
    border: '1px solid #2563eb',
    background: '#1e3a5f',
    color: '#93c5fd',
    cursor: 'pointer',
    fontSize: '0.825rem',
    fontWeight: 500,
  },
  error: {
    color: '#ef4444',
    padding: '0.75rem 1.25rem',
    fontSize: '0.85rem',
  },
  empty: {
    color: '#555',
    textAlign: 'center',
    padding: '2rem 1rem',
  },
  list: {
    overflowY: 'auto',
    padding: '0.5rem 0',
  },
  candidate: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0.75rem 1.25rem',
    borderBottom: '1px solid #222',
    gap: '0.75rem',
  },
  candidateInfo: {
    flex: 1,
    minWidth: 0,
  },
  candidateTitle: {
    fontSize: '0.85rem',
    fontWeight: 500,
    color: '#e0e0e0',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  candidateMeta: {
    fontSize: '0.75rem',
    color: '#666',
    marginTop: '0.2rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
    flexWrap: 'wrap',
  },
  flacTag: {
    background: '#14532d',
    color: '#86efac',
    padding: '0.1rem 0.4rem',
    borderRadius: 3,
    fontSize: '0.65rem',
    fontWeight: 600,
  },
  triedTag: {
    background: '#450a0a',
    color: '#fca5a5',
    padding: '0.1rem 0.4rem',
    borderRadius: 3,
    fontSize: '0.65rem',
    fontWeight: 600,
  },
  artistRow: {
    padding: '0.75rem 1.25rem',
    borderBottom: '1px solid #2a2a2a',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.4rem',
  },
  artistLabel: {
    fontSize: '0.8rem',
    color: '#888',
  },
  artistInputRow: {
    display: 'flex',
    gap: '0.4rem',
    alignItems: 'center',
  },
  artistInput: {
    flex: 1,
    padding: '0.35rem 0.6rem',
    borderRadius: 5,
    border: '1px solid #333',
    background: '#111',
    color: '#e0e0e0',
    fontSize: '0.825rem',
    outline: 'none',
  },
  artistSearchBtn: {
    padding: '0.35rem 0.75rem',
    borderRadius: 5,
    border: '1px solid #2563eb',
    background: '#1e3a5f',
    color: '#93c5fd',
    cursor: 'pointer',
    fontSize: '0.775rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  artistClearBtn: {
    padding: '0.35rem 0.6rem',
    borderRadius: 5,
    border: '1px solid #333',
    background: 'transparent',
    color: '#888',
    cursor: 'pointer',
    fontSize: '0.775rem',
    whiteSpace: 'nowrap',
  },
  selectBtn: {
    padding: '0.35rem 0.75rem',
    borderRadius: 5,
    border: '1px solid #22c55e',
    background: '#052e16',
    color: '#86efac',
    cursor: 'pointer',
    fontSize: '0.775rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
    flexShrink: 0,
  },
}
