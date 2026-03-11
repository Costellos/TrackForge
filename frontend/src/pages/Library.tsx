import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listLibrary, LibraryEntry, listCandidates, selectCandidate, retryRequest, linkJellyfin, cancelRequest, NzbCandidate } from '../api/requests'
import { api } from '../api/client'
import { jellyfinWebUrl, searchLibrary, LibrarySearchItem, getJellyfinItems, linkMusicBrainz, unlinkMusicBrainz } from '../api/library'
import { getReviewTags, saveReviewTags, approveReview, FileTags } from '../api/review'
import { search, ReleaseGroupResult } from '../api/search'
import { useAuthStore } from '../stores/auth'

const STATUS_CONFIG: Record<string, { label: string; style: React.CSSProperties }> = {
  pending_approval: { label: 'Pending', style: { background: '#422006', color: '#fdba74' } },
  approved:         { label: 'Approved', style: { background: '#1e3a5f', color: '#93c5fd' } },
  searching:        { label: 'Searching', style: { background: '#1e3a5f', color: '#93c5fd' } },
  downloading:      { label: 'Downloading', style: { background: '#1e3a5f', color: '#93c5fd' } },
  processing:       { label: 'Processing', style: { background: '#1e3a5f', color: '#93c5fd' } },
  pending_review:   { label: 'Review', style: { background: '#3b0764', color: '#c084fc' } },
  available:        { label: 'Available', style: { background: '#14532d', color: '#86efac' } },
  failed:           { label: 'Failed', style: { background: '#450a0a', color: '#fca5a5' } },
  cancelled:        { label: 'Cancelled', style: { background: '#1c1917', color: '#78716c' } },
}

type Section = 'requested' | 'downloading' | 'processing' | 'pending_review' | 'available' | 'failed' | 'jellyfin'

const SECTION_CONFIG: Record<Section, { label: string; color: string; emptyMsg: string }> = {
  requested:      { label: 'Requested', color: '#fdba74', emptyMsg: 'No pending requests.' },
  downloading:    { label: 'Downloading', color: '#93c5fd', emptyMsg: 'Nothing downloading right now.' },
  processing:     { label: 'Processing', color: '#93c5fd', emptyMsg: 'Nothing being processed.' },
  pending_review: { label: 'Pending Review', color: '#c084fc', emptyMsg: 'Nothing to review.' },
  available:      { label: 'Available', color: '#86efac', emptyMsg: 'No available items.' },
  failed:         { label: 'Failed', color: '#fca5a5', emptyMsg: 'No failed requests.' },
  jellyfin:       { label: 'In Jellyfin', color: '#4ade80', emptyMsg: 'No items in Jellyfin yet.' },
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
      return 'processing'
    case 'pending_review':
      return 'pending_review'
    case 'available':
      return 'available'
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

function LinkModal({ requestId, entryName, onClose }: { requestId: string; entryName: string; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState(entryName)
  const [results, setResults] = useState<LibrarySearchItem[]>([])
  const [searching, setSearching] = useState(false)
  const [linking, setLinking] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSearch() {
    if (!query.trim()) return
    setSearching(true)
    setError(null)
    try {
      const items = await searchLibrary(query.trim())
      setResults(items)
    } catch {
      setError('Search failed')
    } finally {
      setSearching(false)
    }
  }

  async function handleLink(item: LibrarySearchItem) {
    setLinking(item.jellyfin_item_id)
    setError(null)
    try {
      await linkJellyfin(requestId, item.jellyfin_item_id)
      queryClient.invalidateQueries({ queryKey: ['library'] })
      onClose()
    } catch {
      setError('Failed to link')
    } finally {
      setLinking(null)
    }
  }

  return (
    <div style={modalStyles.overlay} onClick={onClose}>
      <div style={modalStyles.modal} onClick={e => e.stopPropagation()}>
        <div style={modalStyles.header}>
          <h3 style={modalStyles.title}>Link to Jellyfin</h3>
          <button style={modalStyles.closeBtn} onClick={onClose}>×</button>
        </div>
        <div style={modalStyles.artistRow}>
          <div style={modalStyles.artistInputRow}>
            <input
              type="text"
              placeholder="Search Jellyfin library..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              style={modalStyles.artistInput}
            />
            <button
              style={modalStyles.artistSearchBtn}
              disabled={!query.trim() || searching}
              onClick={handleSearch}
            >
              {searching ? 'Searching...' : 'Search'}
            </button>
          </div>
        </div>
        {error && <div style={modalStyles.error}>{error}</div>}
        {results.length === 0 && !searching && (
          <div style={modalStyles.empty}>Search for an album in your Jellyfin library to link it.</div>
        )}
        <div style={modalStyles.list}>
          {results.map(item => (
            <div key={item.jellyfin_item_id} style={modalStyles.candidate}>
              <div style={modalStyles.candidateInfo}>
                <div style={modalStyles.candidateTitle}>{item.name}</div>
                <div style={modalStyles.candidateMeta}>
                  {[item.artist_name, item.year].filter(Boolean).join(' · ')}
                </div>
              </div>
              <button
                style={modalStyles.selectBtn}
                onClick={() => handleLink(item)}
                disabled={linking !== null}
              >
                {linking === item.jellyfin_item_id ? 'Linking...' : 'Link'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

interface DisplayEntry extends LibraryEntry {
  _libraryItemId?: string  // set for pure Jellyfin library items (not from requests)
  _isLibraryOnly?: boolean
  _release_mbid?: string | null
  _artist_mbid?: string | null
}

function LinkMusicBrainzModal({ item, onClose }: { item: DisplayEntry; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState(`${item.name} ${item.subtitle?.split(' · ')[0] ?? ''}`.trim())
  const [results, setResults] = useState<ReleaseGroupResult[]>([])
  const [searching, setSearching] = useState(false)
  const [linking, setLinking] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSearch() {
    if (!query.trim()) return
    setSearching(true)
    setError(null)
    try {
      const res = await search(query.trim(), 'album')
      setResults((res.results ?? []) as ReleaseGroupResult[])
    } catch {
      setError('Search failed')
    } finally {
      setSearching(false)
    }
  }

  async function handleLink(mbid: string) {
    if (!item._libraryItemId) return
    setLinking(mbid)
    setError(null)
    try {
      await linkMusicBrainz(item._libraryItemId, mbid)
      queryClient.invalidateQueries({ queryKey: ['jellyfinItems'] })
      onClose()
    } catch {
      setError('Failed to link')
    } finally {
      setLinking(null)
    }
  }

  return (
    <div style={modalStyles.overlay} onClick={onClose}>
      <div style={modalStyles.modal} onClick={e => e.stopPropagation()}>
        <div style={modalStyles.header}>
          <h3 style={modalStyles.title}>Link to MusicBrainz</h3>
          <button style={modalStyles.closeBtn} onClick={onClose}>×</button>
        </div>
        <div style={modalStyles.artistRow}>
          <div style={modalStyles.artistInputRow}>
            <input
              type="text"
              placeholder="Search MusicBrainz..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              style={modalStyles.artistInput}
            />
            <button
              style={modalStyles.artistSearchBtn}
              disabled={!query.trim() || searching}
              onClick={handleSearch}
            >
              {searching ? 'Searching...' : 'Search'}
            </button>
          </div>
        </div>
        {error && <div style={modalStyles.error}>{error}</div>}
        {results.length === 0 && !searching && (
          <div style={modalStyles.empty}>Search MusicBrainz to link this album.</div>
        )}
        <div style={modalStyles.list}>
          {results.filter(rg => rg.mbid).map(rg => (
            <div key={rg.mbid} style={modalStyles.candidate}>
              <div style={modalStyles.candidateInfo}>
                <div style={modalStyles.candidateTitle}>{rg.title}</div>
                <div style={modalStyles.candidateMeta}>
                  {[rg.artists?.[0]?.name, rg.first_release_date?.slice(0, 4), rg.type].filter(Boolean).join(' · ')}
                </div>
              </div>
              <button
                style={modalStyles.selectBtn}
                onClick={() => handleLink(rg.mbid!)}
                disabled={linking !== null}
              >
                {linking === rg.mbid ? 'Linking...' : 'Link'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function TagReviewModal({ requestId, entryName, onClose }: { requestId: string; entryName: string; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [files, setFiles] = useState<FileTags[]>([])
  const [editedTags, setEditedTags] = useState<Record<string, Record<string, string>>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [approving, setApproving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoImportAt, setAutoImportAt] = useState<string | null>(null)

  // Load tags on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await getReviewTags(requestId)
        setFiles(res.files)
        setAutoImportAt(res.auto_import_at)
        const edits: Record<string, Record<string, string>> = {}
        for (const f of res.files) {
          edits[f.filename] = { ...f.tags }
        }
        setEditedTags(edits)
      } catch {
        setError('Failed to load tags')
      } finally {
        setLoading(false)
      }
    })()
  }, [requestId])

  function updateTag(filename: string, key: string, value: string) {
    setEditedTags(prev => ({
      ...prev,
      [filename]: { ...prev[filename], [key]: value },
    }))
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      const fileEdits = Object.entries(editedTags).map(([filename, tags]) => ({ filename, tags }))
      await saveReviewTags(requestId, fileEdits)
      // Reload tags after save
      const res = await getReviewTags(requestId)
      setFiles(res.files)
    } catch {
      setError('Failed to save tags')
    } finally {
      setSaving(false)
    }
  }

  async function handleApprove() {
    setApproving(true)
    setError(null)
    try {
      await approveReview(requestId)
      queryClient.invalidateQueries({ queryKey: ['library'] })
      onClose()
    } catch {
      setError('Failed to approve')
    } finally {
      setApproving(false)
    }
  }

  // Countdown timer
  const [countdown, setCountdown] = useState('')
  useEffect(() => {
    if (!autoImportAt) return
    const iv = setInterval(() => {
      const diff = new Date(autoImportAt).getTime() - Date.now()
      if (diff <= 0) {
        setCountdown('Auto-importing...')
        clearInterval(iv)
        return
      }
      const m = Math.floor(diff / 60000)
      const s = Math.floor((diff % 60000) / 1000)
      setCountdown(`Auto-import in ${m}:${s.toString().padStart(2, '0')}`)
    }, 1000)
    return () => clearInterval(iv)
  }, [autoImportAt])

  const TAG_LABELS: Record<string, string> = {
    tracknumber: '#', title: 'Title', artist: 'Artist',
    albumartist: 'Album Artist', album: 'Album', date: 'Year', genre: 'Genre',
  }
  const TAG_ORDER = ['tracknumber', 'title', 'artist', 'albumartist', 'album', 'date', 'genre']

  return (
    <div style={modalStyles.overlay} onClick={onClose}>
      <div style={{ ...modalStyles.modal, maxWidth: 900 }} onClick={e => e.stopPropagation()}>
        <div style={modalStyles.header}>
          <div>
            <h3 style={modalStyles.title}>Review Tags: {entryName}</h3>
            {countdown && <span style={{ fontSize: '0.75rem', color: '#c084fc' }}>{countdown}</span>}
          </div>
          <button style={modalStyles.closeBtn} onClick={onClose}>×</button>
        </div>

        {error && <div style={modalStyles.error}>{error}</div>}

        {loading && <div style={modalStyles.empty}>Loading tags...</div>}

        {!loading && files.length === 0 && (
          <div style={modalStyles.empty}>No audio files found.</div>
        )}

        {!loading && files.length > 0 && (
          <div style={{ overflowX: 'auto', overflowY: 'auto', maxHeight: '55vh' }}>
            <table style={reviewStyles.table}>
              <thead>
                <tr>
                  {TAG_ORDER.map(key => (
                    <th key={key} style={reviewStyles.th}>{TAG_LABELS[key] || key}</th>
                  ))}
                  <th style={reviewStyles.th}>Format</th>
                </tr>
              </thead>
              <tbody>
                {files.map(f => (
                  <tr key={f.filename}>
                    {TAG_ORDER.map(key => (
                      <td key={key} style={reviewStyles.td}>
                        <input
                          style={reviewStyles.input}
                          value={editedTags[f.filename]?.[key] ?? ''}
                          onChange={e => updateTag(f.filename, key, e.target.value)}
                        />
                      </td>
                    ))}
                    <td style={{ ...reviewStyles.td, color: '#888', fontSize: '0.7rem' }}>
                      {f.format.toUpperCase()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.5rem', padding: '0.75rem 1.25rem', borderTop: '1px solid #2a2a2a', justifyContent: 'flex-end' }}>
          <button
            style={{ ...styles.linkBtn, padding: '0.4rem 1rem' }}
            onClick={handleSave}
            disabled={saving || approving || loading}
          >
            {saving ? 'Saving...' : 'Save Tags'}
          </button>
          <button
            style={{ ...reviewStyles.approveBtn }}
            onClick={handleApprove}
            disabled={saving || approving || loading}
          >
            {approving ? 'Importing...' : 'Approve & Import'}
          </button>
        </div>
      </div>
    </div>
  )
}

function EntryCard({ entry, isAdmin, jellyfinUrl, section }: { entry: DisplayEntry; isAdmin: boolean; jellyfinUrl?: string | null; section: Section }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showCandidates, setShowCandidates] = useState(false)
  const [showLink, setShowLink] = useState(false)
  const [showMbLink, setShowMbLink] = useState(false)
  const [showTagReview, setShowTagReview] = useState(false)
  const [unlinking, setUnlinking] = useState(false)
  const [removing, setRemoving] = useState(false)
  const typeLabel = entry.target_type === 'artist' ? 'Artist' : entry.target_type === 'song' ? 'Song' : 'Album'
  const meta = [entry.subtitle, entry.year].filter(Boolean).join(' · ')
  const isCollection = entry.target_type === 'collection'
  const isLibraryOnly = entry._isLibraryOnly

  // Cover art: prefer MBID, fall back to Jellyfin image proxy
  let coverUrl: string | null = null
  if (entry.mbid) {
    coverUrl = `https://coverartarchive.org/release-group/${entry.mbid}/front-250`
  } else if (entry._release_mbid) {
    coverUrl = `https://coverartarchive.org/release/${entry._release_mbid}/front-250`
  } else if (entry.jellyfin_item_id) {
    coverUrl = `${api.defaults.baseURL}/library/image/${entry.jellyfin_item_id}`
  }

  function handleClick() {
    if (entry.mbid) {
      navigate(isCollection ? `/album/${entry.mbid}` : `/artist/${entry.mbid}`)
    }
  }

  async function handleUnlinkMb(e: React.MouseEvent) {
    e.stopPropagation()
    if (!entry._libraryItemId) return
    if (!confirm(`Unlink MusicBrainz from "${entry.name}"?`)) return
    setUnlinking(true)
    try {
      await unlinkMusicBrainz(entry._libraryItemId)
      queryClient.invalidateQueries({ queryKey: ['jellyfinItems'] })
    } catch {
      // ignore
    } finally {
      setUnlinking(false)
    }
  }

  async function handleRemove(e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm(`Remove "${entry.name}" from your library?`)) return
    setRemoving(true)
    try {
      await cancelRequest(entry.id)
      queryClient.invalidateQueries({ queryKey: ['library'] })
    } catch {
      // ignore
    } finally {
      setRemoving(false)
    }
  }

  return (
    <>
      <div style={styles.card} onClick={handleClick}>
        {isCollection && <CoverArt url={coverUrl} size={44} />}
        <div style={styles.cardLeft}>
          <span style={styles.typeTag}>{typeLabel}</span>
          <div style={styles.cardTitle}>{entry.name}</div>
          {meta && <div style={styles.cardMeta}>{meta}</div>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {section !== 'jellyfin' && !isLibraryOnly && (
            <button
              style={styles.removeBtn}
              onClick={handleRemove}
              disabled={removing}
            >
              {removing ? '...' : '×'}
            </button>
          )}
          {entry.status === 'pending_review' && isAdmin && (
            <button
              style={reviewStyles.reviewBtn}
              onClick={e => { e.stopPropagation(); setShowTagReview(true) }}
            >
              Review Tags
            </button>
          )}
          {entry.status === 'available' && !entry.jellyfin_item_id && isAdmin && (
            <button
              style={styles.linkBtn}
              onClick={e => { e.stopPropagation(); setShowLink(true) }}
            >
              Link
            </button>
          )}
          {section === 'jellyfin' && entry._libraryItemId && isAdmin && !entry.mbid && (
            <button
              style={styles.linkBtn}
              onClick={e => { e.stopPropagation(); setShowMbLink(true) }}
            >
              Link to MB
            </button>
          )}
          {section === 'jellyfin' && entry._libraryItemId && isAdmin && entry.mbid && (
            <>
              <button
                style={styles.unlinkBtn}
                onClick={handleUnlinkMb}
                disabled={unlinking}
              >
                {unlinking ? '...' : 'Unlink MB'}
              </button>
              <button
                style={styles.linkBtn}
                onClick={e => { e.stopPropagation(); setShowMbLink(true) }}
              >
                Relink
              </button>
            </>
          )}
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
      {showLink && (
        <LinkModal requestId={entry.id} entryName={entry.name} onClose={() => setShowLink(false)} />
      )}
      {showMbLink && (
        <LinkMusicBrainzModal item={entry} onClose={() => setShowMbLink(false)} />
      )}
      {showTagReview && (
        <TagReviewModal requestId={entry.id} entryName={entry.name} onClose={() => setShowTagReview(false)} />
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

  const { data: jellyfinData } = useQuery({
    queryKey: ['jellyfinItems'],
    queryFn: getJellyfinItems,
    staleTime: 1000 * 60,
  })

  const entries = libraryData?.entries ?? []
  const jellyfinUrl = jellyfinData?.jellyfin_url ?? libraryData?.jellyfin_url ?? null

  // Group into sections
  const sections: Record<Section, DisplayEntry[]> = {
    requested: [],
    downloading: [],
    processing: [],
    pending_review: [],
    available: [],
    failed: [],
    jellyfin: [],
  }
  for (const entry of entries) {
    sections[classifyEntry(entry)].push(entry)
  }

  // Build lookup: jellyfin_item_id → library item id
  const jfIdToLibraryId: Record<string, string> = {}
  for (const item of jellyfinData?.items ?? []) {
    jfIdToLibraryId[item.jellyfin_item_id] = item.id
  }

  // Enrich request-based jellyfin entries with library item IDs
  for (const entry of sections.jellyfin) {
    if (entry.jellyfin_item_id && jfIdToLibraryId[entry.jellyfin_item_id]) {
      entry._libraryItemId = jfIdToLibraryId[entry.jellyfin_item_id]
    }
  }

  // Merge Jellyfin library items not already represented by requests
  const requestJfIds = new Set(
    sections.jellyfin.map(e => e.jellyfin_item_id).filter(Boolean)
  )
  for (const item of jellyfinData?.items ?? []) {
    if (requestJfIds.has(item.jellyfin_item_id)) continue
    sections.jellyfin.push({
      id: item.id,
      target_type: 'collection',
      target_id: item.id,
      status: 'available',
      user_notes: null,
      created_at: item.date_created ?? '',
      name: item.name,
      subtitle: item.artist_name,
      year: item.year ? String(item.year) : null,
      requested_by: null,
      mbid: item.mbid,
      jellyfin_item_id: item.jellyfin_item_id,
      _libraryItemId: item.id,
      _isLibraryOnly: true,
      _release_mbid: item.release_mbid,
      _artist_mbid: item.artist_mbid,
    })
  }

  const totalCount = entries.length + (jellyfinData?.items ?? []).filter(
    item => !requestJfIds.has(item.jellyfin_item_id)
  ).length
  const sectionOrder: Section[] = ['requested', 'downloading', 'processing', 'pending_review', 'available', 'failed', 'jellyfin']
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
  linkBtn: {
    padding: '0.3rem 0.65rem',
    borderRadius: 5,
    border: '1px solid #2563eb',
    background: '#1e3a5f',
    color: '#93c5fd',
    cursor: 'pointer',
    fontSize: '0.75rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  unlinkBtn: {
    padding: '0.3rem 0.65rem',
    borderRadius: 5,
    border: '1px solid #92400e',
    background: '#422006',
    color: '#fbbf24',
    cursor: 'pointer',
    fontSize: '0.75rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  removeBtn: {
    padding: '0.15rem 0.45rem',
    borderRadius: 4,
    border: '1px solid #333',
    background: 'transparent',
    color: '#666',
    cursor: 'pointer',
    fontSize: '0.85rem',
    lineHeight: 1,
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

const reviewStyles: Record<string, React.CSSProperties> = {
  reviewBtn: {
    padding: '0.3rem 0.65rem',
    borderRadius: 5,
    border: '1px solid #7c3aed',
    background: '#3b0764',
    color: '#c084fc',
    cursor: 'pointer',
    fontSize: '0.75rem',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  approveBtn: {
    padding: '0.4rem 1rem',
    borderRadius: 6,
    border: '1px solid #22c55e',
    background: '#052e16',
    color: '#86efac',
    cursor: 'pointer',
    fontSize: '0.825rem',
    fontWeight: 500,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '0.8rem',
  },
  th: {
    padding: '0.4rem 0.5rem',
    textAlign: 'left',
    color: '#888',
    fontSize: '0.7rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    borderBottom: '1px solid #2a2a2a',
    whiteSpace: 'nowrap',
  },
  td: {
    padding: '0.25rem 0.3rem',
    borderBottom: '1px solid #1a1a1a',
  },
  input: {
    width: '100%',
    padding: '0.25rem 0.4rem',
    borderRadius: 3,
    border: '1px solid #333',
    background: '#111',
    color: '#e0e0e0',
    fontSize: '0.78rem',
    outline: 'none',
    boxSizing: 'border-box',
  },
}
