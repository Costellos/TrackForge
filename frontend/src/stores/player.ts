import { getTrackPreview } from '../api/search'

export type PlayerState = 'idle' | 'loading' | 'playing' | 'paused' | 'none'

interface PlayerData {
  state: PlayerState
  trackTitle: string | null
  artistName: string | null
  recordingMbid: string | null
  source: string | null
  currentTime: number
  duration: number
  volume: number
}

const VOLUME_KEY = 'trackforge_volume'
let audio: HTMLAudioElement | null = null
let animFrame: number | null = null

let data: PlayerData = {
  state: 'idle',
  trackTitle: null,
  artistName: null,
  recordingMbid: null,
  source: null,
  currentTime: 0,
  duration: 0,
  volume: parseFloat(localStorage.getItem(VOLUME_KEY) ?? '0.5'),
}

const listeners = new Set<() => void>()

function notify() {
  listeners.forEach(cb => cb())
}

function updateTime() {
  if (audio && data.state === 'playing') {
    data = { ...data, currentTime: audio.currentTime, duration: audio.duration || 0 }
    notify()
    animFrame = requestAnimationFrame(updateTime)
  }
}

export function getPlayerData(): PlayerData {
  return data
}

export function subscribePlayer(cb: () => void) {
  listeners.add(cb)
  return () => { listeners.delete(cb) }
}

// Attempt to mimic a logarithmic (perceptual) volume curve: slider 0–1 maps to audio 0–1
// using x^2 so the midpoint (~50%) feels like ~25% loudness, which matches human hearing.
function toAudioVolume(sliderValue: number): number {
  return sliderValue * sliderValue
}

export function setVolume(v: number) {
  data = { ...data, volume: v }
  localStorage.setItem(VOLUME_KEY, String(v))
  if (audio) audio.volume = toAudioVolume(v)
  notify()
}

export function seekTo(time: number) {
  if (audio) {
    audio.currentTime = time
    data = { ...data, currentTime: time }
    notify()
  }
}

export function togglePlayPause() {
  if (!audio) return
  if (data.state === 'playing') {
    audio.pause()
    if (animFrame) cancelAnimationFrame(animFrame)
    data = { ...data, state: 'paused' }
    notify()
  } else if (data.state === 'paused') {
    audio.play()
    data = { ...data, state: 'playing' }
    notify()
    animFrame = requestAnimationFrame(updateTime)
  }
}

export function stopPlayer() {
  if (audio) {
    audio.pause()
    audio = null
  }
  if (animFrame) cancelAnimationFrame(animFrame)
  data = { ...data, state: 'idle', trackTitle: null, artistName: null, recordingMbid: null, source: null, currentTime: 0, duration: 0 }
  notify()
}

export async function playTrack(recordingMbid: string, title: string, artist: string | null) {
  // If same track and paused, resume
  if (data.recordingMbid === recordingMbid && data.state === 'paused' && audio) {
    audio.play()
    data = { ...data, state: 'playing' }
    notify()
    animFrame = requestAnimationFrame(updateTime)
    return
  }

  // If same track and playing, pause
  if (data.recordingMbid === recordingMbid && data.state === 'playing' && audio) {
    togglePlayPause()
    return
  }

  // Stop current
  if (audio) {
    audio.pause()
    audio = null
  }
  if (animFrame) cancelAnimationFrame(animFrame)

  data = { ...data, state: 'loading', trackTitle: title, artistName: artist, recordingMbid, source: null, currentTime: 0, duration: 0 }
  notify()

  try {
    const result = await getTrackPreview(recordingMbid)

    if (result.source === 'none' || !result.url) {
      data = { ...data, state: 'none', source: 'none' }
      notify()
      return
    }

    if (result.source === 'youtube') {
      window.open(result.url, '_blank', 'noopener')
      data = { ...data, state: 'idle', source: 'youtube' }
      notify()
      return
    }

    const newAudio = new Audio(result.url)
    newAudio.volume = toAudioVolume(data.volume)
    audio = newAudio

    newAudio.addEventListener('loadedmetadata', () => {
      data = { ...data, duration: newAudio.duration }
      notify()
    })

    newAudio.addEventListener('ended', () => {
      if (animFrame) cancelAnimationFrame(animFrame)
      data = { ...data, state: 'idle', currentTime: 0 }
      notify()
    })

    newAudio.addEventListener('error', () => {
      if (animFrame) cancelAnimationFrame(animFrame)
      data = { ...data, state: 'none' }
      notify()
    })

    await newAudio.play()
    data = { ...data, state: 'playing', source: result.source }
    notify()
    animFrame = requestAnimationFrame(updateTime)
  } catch {
    data = { ...data, state: 'none' }
    notify()
  }
}
