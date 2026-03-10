import { useState, useRef, useEffect } from 'react'
import { getTrackPreview, PreviewResult } from '../api/search'

type PreviewState = 'idle' | 'loading' | 'playing' | 'paused' | 'none'

// Global audio element — only one track can play at a time
let globalAudio: HTMLAudioElement | null = null
let globalStopCallback: (() => void) | null = null

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
