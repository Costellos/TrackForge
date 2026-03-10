import { useSyncExternalStore } from 'react'
import { getPlayerData, subscribePlayer, setVolume, seekTo, togglePlayPause, stopPlayer } from '../stores/player'

function formatTime(s: number): string {
  if (!s || !isFinite(s)) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export default function GlobalPlayer() {
  const player = useSyncExternalStore(subscribePlayer, getPlayerData)

  // Don't render if nothing has been played yet
  if (player.state === 'idle' && !player.trackTitle) return null

  const progress = player.duration > 0 ? (player.currentTime / player.duration) * 100 : 0
  const isActive = player.state === 'playing' || player.state === 'paused' || player.state === 'loading'

  return (
    <div style={styles.bar}>
      {/* Progress bar (clickable) */}
      <div
        style={styles.progressTrack}
        onClick={e => {
          if (!player.duration) return
          const rect = e.currentTarget.getBoundingClientRect()
          const pct = (e.clientX - rect.left) / rect.width
          seekTo(pct * player.duration)
        }}
      >
        <div style={{ ...styles.progressFill, width: `${progress}%` }} />
      </div>

      <div style={styles.inner}>
        {/* Track info */}
        <div style={styles.trackInfo}>
          <div style={styles.trackTitle}>{player.trackTitle || 'No track'}</div>
          {player.artistName && <div style={styles.trackArtist}>{player.artistName}</div>}
        </div>

        {/* Controls */}
        <div style={styles.controls}>
          {player.state === 'loading' ? (
            <span style={styles.loadingText}>Loading...</span>
          ) : player.state === 'none' ? (
            <span style={styles.noneText}>No preview available</span>
          ) : (
            <>
              <button style={styles.playBtn} onClick={togglePlayPause} disabled={!isActive}>
                {player.state === 'playing' ? '\u275A\u275A' : '\u25B6'}
              </button>
              <span style={styles.time}>
                {formatTime(player.currentTime)} / {formatTime(player.duration)}
              </span>
            </>
          )}
        </div>

        {/* Volume + close */}
        <div style={styles.right}>
          <span style={styles.volIcon}>
            {player.volume === 0 ? '\u{1F507}' : player.volume < 0.5 ? '\u{1F509}' : '\u{1F50A}'}
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={player.volume}
            onChange={e => setVolume(parseFloat(e.target.value))}
            style={styles.volSlider}
            title={`Volume: ${Math.round(player.volume * 100)}%`}
          />
          <button style={styles.closeBtn} onClick={stopPlayer} title="Close player">&times;</button>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  bar: {
    position: 'fixed',
    bottom: 0,
    left: 0,
    right: 0,
    background: '#111',
    borderTop: '1px solid #2a2a2a',
    zIndex: 100,
  },
  progressTrack: {
    height: 3,
    background: '#222',
    cursor: 'pointer',
    position: 'relative',
  },
  progressFill: {
    height: '100%',
    background: '#2563eb',
    borderRadius: '0 2px 2px 0',
    transition: 'width 0.1s linear',
  },
  inner: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0.5rem 1.5rem',
    maxWidth: 1200,
    margin: '0 auto',
    gap: '1.5rem',
  },
  trackInfo: {
    flex: 1,
    minWidth: 0,
  },
  trackTitle: {
    fontSize: '0.85rem',
    fontWeight: 600,
    color: '#e0e0e0',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  trackArtist: {
    fontSize: '0.75rem',
    color: '#888',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  controls: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    flexShrink: 0,
  },
  playBtn: {
    width: 32,
    height: 32,
    borderRadius: '50%',
    border: '1px solid #444',
    background: 'transparent',
    color: '#e0e0e0',
    fontSize: '0.8rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 0,
  },
  time: {
    fontSize: '0.75rem',
    color: '#666',
    fontVariantNumeric: 'tabular-nums',
    minWidth: 80,
  },
  loadingText: {
    fontSize: '0.8rem',
    color: '#888',
  },
  noneText: {
    fontSize: '0.8rem',
    color: '#555',
  },
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
    flexShrink: 0,
  },
  volIcon: {
    fontSize: '0.8rem',
    color: '#666',
    userSelect: 'none',
  },
  volSlider: {
    width: 80,
    height: 4,
    accentColor: '#2563eb',
    cursor: 'pointer',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#555',
    fontSize: '1.2rem',
    cursor: 'pointer',
    padding: '0 0.25rem',
    marginLeft: '0.25rem',
  },
}
