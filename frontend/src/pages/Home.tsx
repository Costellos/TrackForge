import { useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listLibrary, LibraryEntry } from '../api/requests'
import { getArtistImages } from '../api/search'
import { getTrendingReleaseGroups, getTrendingArtists, TrendingReleaseGroup, TrendingArtist } from '../api/trending'
import { getRecentlyAdded, RecentlyAddedItem, recentlyAddedArtUrl, resolveJellyfinItem, jellyfinWebUrl } from '../api/library'
import { useAuthStore } from '../stores/auth'

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  pending_approval: { label: 'Pending',     color: '#fbbf24', bg: '#422006' },
  approved:         { label: 'Approved',    color: '#60a5fa', bg: '#172554' },
  searching:        { label: 'Searching',   color: '#c084fc', bg: '#3b0764' },
  downloading:      { label: 'Downloading', color: '#38bdf8', bg: '#0c4a6e' },
  processing:       { label: 'Processing',  color: '#a78bfa', bg: '#2e1065' },
  available:        { label: 'Available',   color: '#4ade80', bg: '#14532d' },
  failed:           { label: 'Failed',      color: '#f87171', bg: '#450a0a' },
  cancelled:        { label: 'Cancelled',   color: '#737373', bg: '#262626' },
  rejected:         { label: 'Rejected',    color: '#fb923c', bg: '#431407' },
}

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, color: '#aaa', bg: '#333' }
  return (
    <span style={{ ...styles.statusBadge, color: cfg.color, background: cfg.bg }}>
      {cfg.label}
    </span>
  )
}

function CoverArt({ url, size }: { url: string | null; size: number }) {
  const [failed, setFailed] = useState(false)
  const box: React.CSSProperties = {
    width: size,
    height: size,
    borderRadius: 6,
    flexShrink: 0,
    background: '#1e1e1e',
    border: '1px solid #2a2a2a',
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

function formatListenCount(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`
  return String(count)
}

// ─── Card Components ───────────────────────

function LibraryCard({ entry }: { entry: LibraryEntry }) {
  const navigate = useNavigate()
  const isCollection = entry.target_type === 'collection'

  function handleClick() {
    if (entry.mbid) {
      navigate(isCollection ? `/album/${entry.mbid}` : `/artist/${entry.mbid}`)
    }
  }

  const artUrl = isCollection && entry.mbid
    ? `https://coverartarchive.org/release-group/${entry.mbid}/front-250`
    : null

  return (
    <div style={styles.card} onClick={handleClick}>
      <CoverArt url={artUrl} size={140} />
      <div style={styles.cardBody}>
        <div style={styles.cardTitle}>{entry.name}</div>
        {entry.subtitle && <div style={styles.cardSub}>{entry.subtitle}</div>}
        <div style={styles.cardMeta}>
          {entry.year && <span>{entry.year}</span>}
          <StatusBadge status={entry.status} />
        </div>
      </div>
    </div>
  )
}

function TrendingAlbumCard({ item }: { item: TrendingReleaseGroup }) {
  const navigate = useNavigate()

  function handleClick() {
    if (item.release_group_mbid) {
      navigate(`/album/${item.release_group_mbid}`)
    }
  }

  // Use caa_release_mbid for cover art (more reliable than release_group_mbid)
  const artUrl = item.caa_release_mbid
    ? `https://coverartarchive.org/release/${item.caa_release_mbid}/front-250`
    : item.release_group_mbid
      ? `https://coverartarchive.org/release-group/${item.release_group_mbid}/front-250`
      : null

  return (
    <div style={styles.card} onClick={handleClick}>
      <CoverArt url={artUrl} size={140} />
      <div style={styles.cardBody}>
        <div style={styles.cardTitle}>{item.title}</div>
        <div style={styles.cardSub}>{item.artist_name}</div>
        {item.listen_count != null && (
          <div style={styles.cardMeta}>
            <span>{formatListenCount(item.listen_count)} plays</span>
          </div>
        )}
      </div>
    </div>
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

function TrendingArtistCard({ item }: { item: TrendingArtist }) {
  const navigate = useNavigate()

  function handleClick() {
    if (item.artist_mbid) {
      navigate(`/artist/${item.artist_mbid}`)
    }
  }

  return (
    <div style={styles.card} onClick={handleClick}>
      <ArtistThumb mbid={item.artist_mbid} size={140} />
      <div style={styles.cardBody}>
        <div style={styles.cardTitle}>{item.artist_name}</div>
        {item.listen_count != null && (
          <div style={styles.cardMeta}>
            <span>{formatListenCount(item.listen_count)} plays</span>
          </div>
        )}
      </div>
    </div>
  )
}

function RecentlyAddedCard({ item, jellyfinUrl }: { item: RecentlyAddedItem; jellyfinUrl?: string | null }) {
  const navigate = useNavigate()
  const [resolving, setResolving] = useState(false)

  async function handleClick() {
    if (!item.jellyfin_item_id || resolving) return
    setResolving(true)
    try {
      const resolved = await resolveJellyfinItem(item.jellyfin_item_id)
      if (resolved) navigate(`/album/${resolved}`)
    } finally {
      setResolving(false)
    }
  }

  const artUrl = recentlyAddedArtUrl(item)

  return (
    <div style={{ ...styles.card, cursor: 'pointer' }} onClick={handleClick}>
      <CoverArt url={artUrl} size={140} />
      <div style={styles.cardBody}>
        <div style={styles.cardTitle}>{item.name}</div>
        <div style={styles.cardSub}>{item.artist_name}</div>
        <div style={styles.cardMeta}>
          {item.year && <span>{item.year}</span>}
          {jellyfinUrl && item.jellyfin_item_id
            ? <a href={jellyfinWebUrl(jellyfinUrl, item.jellyfin_item_id)} target="_blank" rel="noopener noreferrer" style={{ ...styles.inLibraryBadge, textDecoration: 'none' }} onClick={e => e.stopPropagation()}>Jellyfin ↗</a>
            : <span style={styles.inLibraryBadge}>In Library</span>
          }
        </div>
      </div>
    </div>
  )
}

// ─── Scroll Row ────────────────────────────

function ScrollRow({ title, children }: { title: string; children: React.ReactNode }) {
  const scrollRef = useRef<HTMLDivElement>(null)

  function scroll(dir: number) {
    scrollRef.current?.scrollBy({ left: dir * 320, behavior: 'smooth' })
  }

  return (
    <section style={styles.section}>
      <div style={styles.sectionHeader}>
        <h2 style={styles.sectionTitle}>{title}</h2>
        <div style={styles.arrows}>
          <button style={styles.arrowBtn} onClick={() => scroll(-1)}>&lsaquo;</button>
          <button style={styles.arrowBtn} onClick={() => scroll(1)}>&rsaquo;</button>
        </div>
      </div>
      <div ref={scrollRef} style={styles.scrollContainer}>
        {children}
      </div>
    </section>
  )
}

// ─── Page ──────────────────────────────────

export default function Home() {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'admin' || user?.role === 'moderator'

  const { data: libraryData } = useQuery({
    queryKey: ['library'],
    queryFn: listLibrary,
    staleTime: 30_000,
  })

  const { data: trendingAlbums } = useQuery({
    queryKey: ['trending', 'release-groups'],
    queryFn: () => getTrendingReleaseGroups('week', 20),
    staleTime: 60_000 * 30,
  })

  const { data: trendingArtists } = useQuery({
    queryKey: ['trending', 'artists'],
    queryFn: () => getTrendingArtists('week', 20),
    staleTime: 60_000 * 30,
  })

  const { data: recentlyAddedData } = useQuery({
    queryKey: ['library', 'recently-added'],
    queryFn: () => getRecentlyAdded(20),
    staleTime: 60_000 * 5,
  })

  const entries = libraryData?.entries ?? []
  const recentlyAddedItems = recentlyAddedData?.items ?? []
  const jellyfinUrl = recentlyAddedData?.jellyfin_url ?? null

  // Library sections
  const recentlyAvailable = entries.filter(e => e.status === 'available').slice(0, 20)
  const inProgress = entries.filter(e => ['approved', 'searching', 'downloading', 'processing'].includes(e.status)).slice(0, 20)
  const pendingApproval = entries.filter(e => e.status === 'pending_approval').slice(0, 20)
  const recentRequests = entries.slice(0, 20)
  const failed = entries.filter(e => e.status === 'failed').slice(0, 20)

  const hasTrending = (trendingAlbums ?? []).length > 0 || (trendingArtists ?? []).length > 0
  const hasLibrary = entries.length > 0 || recentlyAddedItems.length > 0

  return (
    <div style={styles.page}>
      <div style={styles.hero}>
        <h1 style={styles.heroTitle}>TrackForge</h1>
        <p style={styles.heroSub}>Self-hosted music request platform</p>
      </div>

      {!hasLibrary && !hasTrending && (
        <div style={styles.empty}>
          <div style={styles.emptyTitle}>Nothing here yet</div>
          <div style={styles.emptySub}>Head over to Search to request your first album or artist.</div>
        </div>
      )}

      {/* Trending sections */}
      {(trendingAlbums ?? []).length > 0 && (
        <ScrollRow title="Trending Albums">
          {(trendingAlbums ?? []).map((item, i) => (
            <TrendingAlbumCard key={item.release_group_mbid ?? i} item={item} />
          ))}
        </ScrollRow>
      )}

      {(trendingArtists ?? []).length > 0 && (
        <ScrollRow title="Trending Artists">
          {(trendingArtists ?? []).map((item, i) => (
            <TrendingArtistCard key={item.artist_mbid ?? i} item={item} />
          ))}
        </ScrollRow>
      )}

      {/* Jellyfin library */}
      {recentlyAddedItems.length > 0 && (
        <ScrollRow title="Recently Added to Library">
          {recentlyAddedItems.map((item, i) => (
            <RecentlyAddedCard key={item.jellyfin_item_id ?? i} item={item} jellyfinUrl={jellyfinUrl} />
          ))}
        </ScrollRow>
      )}

      {/* Request sections */}
      {recentlyAvailable.length > 0 && (
        <ScrollRow title="Recently Available">
          {recentlyAvailable.map(e => <LibraryCard key={e.id} entry={e} />)}
        </ScrollRow>
      )}

      {inProgress.length > 0 && (
        <ScrollRow title="In Progress">
          {inProgress.map(e => <LibraryCard key={e.id} entry={e} />)}
        </ScrollRow>
      )}

      {isAdmin && pendingApproval.length > 0 && (
        <ScrollRow title="Pending Approval">
          {pendingApproval.map(e => <LibraryCard key={e.id} entry={e} />)}
        </ScrollRow>
      )}

      {isAdmin && failed.length > 0 && (
        <ScrollRow title="Failed">
          {failed.map(e => <LibraryCard key={e.id} entry={e} />)}
        </ScrollRow>
      )}

      {recentRequests.length > 0 && (
        <ScrollRow title="Recent Requests">
          {recentRequests.map(e => <LibraryCard key={e.id} entry={e} />)}
        </ScrollRow>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    maxWidth: 1200,
    margin: '0 auto',
    padding: '0 1rem 3rem',
  },
  hero: {
    padding: '2.5rem 0 1.5rem',
  },
  heroTitle: {
    fontSize: '2rem',
    fontWeight: 700,
    color: '#f0f0f0',
    margin: 0,
  },
  heroSub: {
    color: '#666',
    marginTop: '0.25rem',
    fontSize: '0.95rem',
  },
  empty: {
    textAlign: 'center',
    padding: '4rem 1rem',
  },
  emptyTitle: {
    fontSize: '1.25rem',
    fontWeight: 600,
    color: '#888',
    marginBottom: '0.5rem',
  },
  emptySub: {
    color: '#555',
    fontSize: '0.9rem',
  },
  section: {
    marginBottom: '2rem',
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '0.75rem',
  },
  sectionTitle: {
    fontSize: '1.25rem',
    fontWeight: 600,
    color: '#e0e0e0',
    margin: 0,
  },
  arrows: {
    display: 'flex',
    gap: '0.25rem',
  },
  arrowBtn: {
    width: 28,
    height: 28,
    borderRadius: 6,
    border: '1px solid #333',
    background: '#1a1a1a',
    color: '#aaa',
    fontSize: '1.1rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    lineHeight: 1,
  },
  scrollContainer: {
    display: 'flex',
    gap: '0.75rem',
    overflowX: 'auto',
    paddingBottom: '0.5rem',
    scrollbarWidth: 'thin',
    scrollbarColor: '#333 transparent',
  },
  card: {
    flexShrink: 0,
    width: 140,
    cursor: 'pointer',
    borderRadius: 8,
    overflow: 'hidden',
    transition: 'transform 0.15s',
  },
  cardBody: {
    padding: '0.5rem 0.125rem',
  },
  cardTitle: {
    fontSize: '0.825rem',
    fontWeight: 600,
    color: '#e0e0e0',
    lineHeight: 1.3,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  cardSub: {
    fontSize: '0.725rem',
    color: '#777',
    marginTop: '0.15rem',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  cardMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.35rem',
    marginTop: '0.3rem',
    fontSize: '0.7rem',
    color: '#555',
  },
  statusBadge: {
    padding: '0.1rem 0.4rem',
    borderRadius: 3,
    fontSize: '0.65rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.03em',
    whiteSpace: 'nowrap',
  },
  inLibraryBadge: {
    padding: '0.1rem 0.35rem',
    borderRadius: 3,
    fontSize: '0.6rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.03em',
    color: '#4ade80',
    background: '#052e16',
    whiteSpace: 'nowrap',
  },
}
