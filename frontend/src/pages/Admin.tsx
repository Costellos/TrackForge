import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listLibrary, approveRequest, cancelRequest, rejectRequest, retryRequest, LibraryEntry } from '../api/requests'

const STATUS_CONFIG: Record<string, { label: string; style: React.CSSProperties }> = {
  pending_approval: { label: 'Pending', style: { background: '#422006', color: '#fdba74' } },
  approved:         { label: 'Approved', style: { background: '#1e3a5f', color: '#93c5fd' } },
  searching:        { label: 'Searching', style: { background: '#1e3a5f', color: '#93c5fd' } },
  downloading:      { label: 'Downloading', style: { background: '#1e3a5f', color: '#93c5fd' } },
  processing:       { label: 'Processing', style: { background: '#1e3a5f', color: '#93c5fd' } },
  available:        { label: 'Available', style: { background: '#14532d', color: '#86efac' } },
  failed:           { label: 'Failed', style: { background: '#450a0a', color: '#fca5a5' } },
  cancelled:        { label: 'Cancelled', style: { background: '#1c1917', color: '#78716c' } },
  rejected:         { label: 'Rejected', style: { background: '#3b0764', color: '#d8b4fe' } },
}

type FilterStatus = 'all' | 'pending_approval' | 'approved' | 'available' | 'failed' | 'cancelled' | 'rejected'

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, style: { background: '#222', color: '#aaa' } }
  return <span style={{ ...styles.badge, ...cfg.style }}>{cfg.label}</span>
}

function ActionButton({
  label, onClick, variant,
}: {
  label: string
  onClick: () => Promise<void>
  variant: 'approve' | 'cancel' | 'retry'
}) {
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)

  async function handle() {
    setLoading(true)
    try {
      await onClick()
      setDone(true)
    } finally {
      setLoading(false)
    }
  }

  if (done) return null

  return (
    <button
      style={variant === 'approve' ? styles.approveBtn : variant === 'retry' ? styles.retryBtn : styles.cancelBtn}
      onClick={handle}
      disabled={loading}
    >
      {loading ? '...' : label}
    </button>
  )
}

function RequestRow({ entry, onAction }: { entry: LibraryEntry; onAction: () => void }) {
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [rejectLoading, setRejectLoading] = useState(false)

  const typeLabel = entry.target_type === 'artist' ? 'Artist' : 'Album'
  const meta = [entry.subtitle, entry.year].filter(Boolean).join(' · ')
  const isPending = entry.status === 'pending_approval'
  const isFailed = entry.status === 'failed'
  const canCancel = !['available', 'cancelled', 'rejected', 'failed'].includes(entry.status)

  async function handleReject() {
    setRejectLoading(true)
    try {
      await rejectRequest(entry.id, rejectReason || undefined)
      onAction()
    } finally {
      setRejectLoading(false)
      setRejectOpen(false)
      setRejectReason('')
    }
  }

  return (
    <div style={styles.row}>
      <div style={styles.rowLeft}>
        <div style={styles.rowTop}>
          <span style={styles.typeTag}>{typeLabel}</span>
          <span style={styles.rowTitle}>{entry.name}</span>
        </div>
        {meta && <div style={styles.rowMeta}>{meta}</div>}
        <div style={styles.rowUser}>
          Requested by <strong style={{ color: '#aaa' }}>{entry.requested_by ?? 'unknown'}</strong>
          <span style={styles.dot}>·</span>
          {new Date(entry.created_at).toLocaleDateString()}
          {entry.user_notes && (
            <><span style={styles.dot}>·</span><em style={{ color: '#666' }}>{entry.user_notes}</em></>
          )}
        </div>
        {rejectOpen && (
          <div style={styles.rejectInline}>
            <input
              style={styles.rejectInput}
              placeholder="Reason (optional)"
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleReject(); if (e.key === 'Escape') setRejectOpen(false) }}
              autoFocus
            />
            <button style={styles.rejectConfirmBtn} onClick={handleReject} disabled={rejectLoading}>
              {rejectLoading ? '...' : 'Confirm'}
            </button>
            <button style={styles.rejectCancelBtn} onClick={() => setRejectOpen(false)}>
              Cancel
            </button>
          </div>
        )}
      </div>
      <div style={styles.rowRight}>
        <StatusBadge status={entry.status} />
        <div style={styles.actions}>
          {isPending && (
            <>
              <ActionButton
                label="Approve"
                variant="approve"
                onClick={async () => { await approveRequest(entry.id); onAction() }}
              />
              <button style={styles.rejectBtn} onClick={() => setRejectOpen(o => !o)}>
                Reject
              </button>
            </>
          )}
          {isFailed && (
            <ActionButton
              label="Retry"
              variant="retry"
              onClick={async () => { await retryRequest(entry.id); onAction() }}
            />
          )}
          {canCancel && (
            <ActionButton
              label="Cancel"
              variant="cancel"
              onClick={async () => { await cancelRequest(entry.id); onAction() }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

const FILTERS: { value: FilterStatus; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'pending_approval', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'available', label: 'Available' },
  { value: 'failed', label: 'Failed' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'cancelled', label: 'Cancelled' },
]

export default function Admin() {
  const [filter, setFilter] = useState<FilterStatus>('all')
  const queryClient = useQueryClient()

  const { data, isFetching, error } = useQuery({
    queryKey: ['admin-requests'],
    queryFn: listLibrary,
    staleTime: 0,
  })

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ['admin-requests'] })
    queryClient.invalidateQueries({ queryKey: ['library'] })
  }

  const filtered = data?.entries?.filter(e =>
    filter === 'all' ? true : e.status === filter
  ) ?? []

  const pendingCount = data?.entries?.filter(e => e.status === 'pending_approval').length ?? 0

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.heading}>Requests</h1>
        {isFetching && <span style={styles.refreshing}>Refreshing...</span>}
      </div>

      <div style={styles.filterRow}>
        {FILTERS.map(f => (
          <button
            key={f.value}
            style={filter === f.value ? { ...styles.filterBtn, ...styles.filterBtnActive } : styles.filterBtn}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
            {f.value === 'pending_approval' && pendingCount > 0 && (
              <span style={styles.pill}>{pendingCount}</span>
            )}
          </button>
        ))}
        <span style={styles.count}>{filtered.length} item{filtered.length !== 1 ? 's' : ''}</span>
      </div>

      {error && (
        <div style={styles.error}>Failed to load requests.</div>
      )}

      {!isFetching && filtered.length === 0 && (
        <div style={styles.empty}>
          {filter === 'pending_approval' ? 'No pending requests.' : 'Nothing here.'}
        </div>
      )}

      <div style={styles.list}>
        {filtered.map(entry => (
          <RequestRow key={entry.id} entry={entry} onAction={refresh} />
        ))}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    maxWidth: 900,
    margin: '0 auto',
    padding: '2rem 1rem',
  },
  header: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '1rem',
    marginBottom: '1.5rem',
  },
  heading: {
    fontSize: '1.75rem',
    fontWeight: 700,
    color: '#f0f0f0',
    margin: 0,
  },
  refreshing: {
    fontSize: '0.8rem',
    color: '#555',
  },
  filterRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    marginBottom: '1.5rem',
    flexWrap: 'wrap',
  },
  filterBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
    padding: '0.35rem 0.875rem',
    borderRadius: 6,
    border: '1px solid #333',
    background: '#1a1a1a',
    color: '#aaa',
    cursor: 'pointer',
    fontSize: '0.825rem',
  },
  filterBtnActive: {
    background: '#2563eb',
    border: '1px solid #2563eb',
    color: '#fff',
  },
  pill: {
    background: '#dc2626',
    color: '#fff',
    borderRadius: 99,
    padding: '0 0.4rem',
    fontSize: '0.7rem',
    fontWeight: 700,
    lineHeight: '1.4',
  },
  count: {
    marginLeft: 'auto',
    fontSize: '0.8rem',
    color: '#555',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0.875rem 1rem',
    background: '#1a1a1a',
    border: '1px solid #2a2a2a',
    borderRadius: 8,
    gap: '1rem',
  },
  rowLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
    minWidth: 0,
  },
  rowTop: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '0.5rem',
  },
  typeTag: {
    fontSize: '0.7rem',
    color: '#555',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.06em',
    fontWeight: 600,
    flexShrink: 0,
  },
  rowTitle: {
    fontWeight: 600,
    fontSize: '0.95rem',
    color: '#f0f0f0',
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  rowMeta: {
    fontSize: '0.75rem',
    color: '#666',
  },
  rowUser: {
    fontSize: '0.775rem',
    color: '#555',
    display: 'flex',
    alignItems: 'center',
    gap: '0.35rem',
    flexWrap: 'wrap' as const,
  },
  dot: {
    color: '#333',
  },
  rowRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    flexShrink: 0,
  },
  actions: {
    display: 'flex',
    gap: '0.4rem',
  },
  badge: {
    padding: '0.3rem 0.75rem',
    borderRadius: 5,
    fontSize: '0.775rem',
    fontWeight: 500,
    whiteSpace: 'nowrap' as const,
  },
  approveBtn: {
    padding: '0.35rem 0.75rem',
    borderRadius: 6,
    border: 'none',
    background: '#15803d',
    color: '#fff',
    fontSize: '0.8rem',
    cursor: 'pointer',
    fontWeight: 500,
  },
  cancelBtn: {
    padding: '0.35rem 0.75rem',
    borderRadius: 6,
    border: '1px solid #333',
    background: 'transparent',
    color: '#666',
    fontSize: '0.8rem',
    cursor: 'pointer',
  },
  retryBtn: {
    padding: '0.35rem 0.75rem',
    borderRadius: 6,
    border: '1px solid #92400e',
    background: 'transparent',
    color: '#fbbf24',
    fontSize: '0.8rem',
    cursor: 'pointer',
  },
  rejectBtn: {
    padding: '0.35rem 0.75rem',
    borderRadius: 6,
    border: '1px solid #4c1d95',
    background: 'transparent',
    color: '#a78bfa',
    fontSize: '0.8rem',
    cursor: 'pointer',
  },
  rejectInline: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    marginTop: '0.5rem',
  },
  rejectInput: {
    padding: '0.3rem 0.6rem',
    borderRadius: 5,
    border: '1px solid #4c1d95',
    background: '#1a1a1a',
    color: '#f0f0f0',
    fontSize: '0.8rem',
    width: 220,
  },
  rejectConfirmBtn: {
    padding: '0.3rem 0.65rem',
    borderRadius: 5,
    border: 'none',
    background: '#6d28d9',
    color: '#fff',
    fontSize: '0.8rem',
    cursor: 'pointer',
  },
  rejectCancelBtn: {
    padding: '0.3rem 0.65rem',
    borderRadius: 5,
    border: '1px solid #333',
    background: 'transparent',
    color: '#666',
    fontSize: '0.8rem',
    cursor: 'pointer',
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
}
