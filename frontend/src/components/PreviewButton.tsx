import { useSyncExternalStore } from 'react'
import { playTrack, getPlayerData, subscribePlayer } from '../stores/player'

export default function PreviewButton({ recordingMbid, title, artist }: {
  recordingMbid: string | null
  title?: string
  artist?: string
}) {
  const player = useSyncExternalStore(subscribePlayer, getPlayerData)

  if (!recordingMbid) {
    return <span style={styles.noPreview}>--</span>
  }

  const isThisTrack = player.recordingMbid === recordingMbid
  const isPlaying = isThisTrack && player.state === 'playing'
  const isLoading = isThisTrack && player.state === 'loading'
  const isNone = isThisTrack && player.state === 'none'

  function handleClick() {
    playTrack(recordingMbid!, title ?? 'Unknown', artist ?? null)
  }

  const icon = isPlaying ? '\u275A\u275A' : isLoading ? '...' : isNone ? '--' : '\u25B6'

  const btnStyle = isNone
    ? styles.noPreview
    : isPlaying
      ? styles.btnPlaying
      : styles.btn

  return (
    <button
      style={btnStyle}
      onClick={handleClick}
      disabled={isLoading || isNone}
      title={
        isNone ? 'No preview available'
        : isPlaying ? 'Pause'
        : 'Play preview'
      }
    >
      {icon}
    </button>
  )
}

const styles: Record<string, React.CSSProperties> = {
  btn: {
    width: 28,
    height: 28,
    borderRadius: '50%',
    border: '1px solid #333',
    background: 'transparent',
    color: '#888',
    fontSize: '0.65rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    padding: 0,
    lineHeight: 1,
  },
  btnPlaying: {
    width: 28,
    height: 28,
    borderRadius: '50%',
    border: '1px solid #22c55e',
    background: '#052e16',
    color: '#4ade80',
    fontSize: '0.6rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    padding: 0,
    lineHeight: 1,
    letterSpacing: '0.05em',
  },
  noPreview: {
    width: 28,
    height: 28,
    borderRadius: '50%',
    border: '1px solid #222',
    background: 'transparent',
    color: '#333',
    fontSize: '0.6rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    padding: 0,
    cursor: 'default',
  },
}
