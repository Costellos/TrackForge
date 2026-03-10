import { useState, useRef, useEffect, useSyncExternalStore } from 'react'
import { getTrackPreview, PreviewResult } from '../api/search'

type PreviewState = 'idle' | 'loading' | 'playing' | 'paused' | 'none'

// Global audio element — only one track can play at a time
let globalAudio: HTMLAudioElement | null = null
let globalStopCallback: (() => void) | null = null

// Global volume (0–1), persisted to localStorage
const VOLUME_KEY = 'trackforge_volume'
let globalVolume = parseFloat(localStorage.getItem(VOLUME_KEY) ?? '0.5')
const volumeListeners = new Set<() => void>()

function getVolume() { return globalVolume }
function subscribeVolume(cb: () => void) { volumeListeners.add(cb); return () => { volumeListeners.delete(cb) } }

export function setGlobalVolume(v: number) {
  globalVolume = v
  localStorage.setItem(VOLUME_KEY, String(v))
  if (globalAudio) globalAudio.volume = v
  volumeListeners.forEach(cb => cb())
}

export function useVolume() {
  return useSyncExternalStore(subscribeVolume, getVolume)
}

export function VolumeSlider() {
  const volume = useVolume()
  return (
    <div style={volumeStyles.wrapper}>
      <span style={volumeStyles.icon}>{volume === 0 ? '\u{1F507}' : volume < 0.5 ? '\u{1F509}' : '\u{1F50A}'}</span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={volume}
        onChange={e => setGlobalVolume(parseFloat(e.target.value))}
        style={volumeStyles.slider}
        title={`Volume: ${Math.round(volume * 100)}%`}
      />
    </div>
  )
}

const volumeStyles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
  },
  icon: {
    fontSize: '0.85rem',
    color: '#666',
    userSelect: 'none',
  },
  slider: {
    width: 80,
    height: 4,
    accentColor: '#2563eb',
    cursor: 'pointer',
  },
}

export default function PreviewButton({ recordingMbid }: { recordingMbid: string | null }) {
  const [state, setState] = useState<PreviewState>('idle')
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const stopRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    return () => {
      // Cleanup on unmount
      if (globalStopCallback === stopRef.current) {
        globalAudio?.pause()
        globalAudio = null
        globalStopCallback = null
      }
    }
  }, [])

  if (!recordingMbid) {
    return <span style={styles.noPreview}>--</span>
  }

  async function handleClick() {
    // If playing, pause
    if (state === 'playing') {
      globalAudio?.pause()
      setState('paused')
      return
    }

    // If paused, resume
    if (state === 'paused' && globalAudio && globalStopCallback === stopRef.current) {
      globalAudio.play()
      setState('playing')
      return
    }

    // Load preview if not loaded yet
    if (!preview) {
      setState('loading')
      try {
        const result = await getTrackPreview(recordingMbid!)
        setPreview(result)

        if (result.source === 'none' || !result.url) {
          setState('none')
          return
        }

        if (result.source === 'youtube') {
          // Open YouTube in new tab
          window.open(result.url, '_blank', 'noopener')
          setState('idle')
          return
        }

        playAudio(result.url)
      } catch {
        setState('none')
      }
      return
    }

    // Already loaded
    if (preview.source === 'none' || !preview.url) {
      return
    }

    if (preview.source === 'youtube') {
      window.open(preview.url, '_blank', 'noopener')
      return
    }

    playAudio(preview.url)
  }

  function playAudio(url: string) {
    // Stop any currently playing track
    if (globalAudio) {
      globalAudio.pause()
      globalStopCallback?.()
    }

    const audio = new Audio(url)
    audio.volume = globalVolume
    globalAudio = audio

    const onStop = () => setState('idle')
    stopRef.current = onStop
    globalStopCallback = onStop

    audio.addEventListener('ended', () => {
      setState('idle')
      globalAudio = null
      globalStopCallback = null
    })

    audio.addEventListener('error', () => {
      setState('none')
      globalAudio = null
      globalStopCallback = null
    })

    audio.play()
    setState('playing')
  }

  const icon = state === 'playing' ? '||' : state === 'paused' ? '\u25B6' : state === 'loading' ? '...' : state === 'none' ? '--' : '\u25B6'

  const btnStyle = state === 'none'
    ? styles.noPreview
    : state === 'playing'
      ? styles.btnPlaying
      : styles.btn

  return (
    <button
      style={btnStyle}
      onClick={handleClick}
      disabled={state === 'loading' || state === 'none'}
      title={
        state === 'none' ? 'No preview available'
        : state === 'playing' ? 'Pause preview'
        : preview?.source === 'youtube' ? 'Open on YouTube'
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
