import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getSettings, updateSettings, AppSettings } from '../api/settings'

function Toggle({
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  label: string
  description: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled: boolean
}) {
  return (
    <div style={styles.settingRow}>
      <div style={styles.settingText}>
        <div style={styles.settingLabel}>{label}</div>
        <div style={styles.settingDesc}>{description}</div>
      </div>
      <button
        style={checked ? styles.toggleOn : styles.toggleOff}
        onClick={() => onChange(!checked)}
        disabled={disabled}
      >
        <div style={checked ? styles.toggleKnobOn : styles.toggleKnobOff} />
      </button>
    </div>
  )
}

export default function Settings() {
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [folderPattern, setFolderPattern] = useState('')
  const [folderPatternDirty, setFolderPatternDirty] = useState(false)
  const [filePattern, setFilePattern] = useState('')
  const [filePatternDirty, setFilePatternDirty] = useState(false)

  const { data, isFetching } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
    staleTime: 0,
  })

  // Sync patterns from server data
  if (data && !folderPatternDirty && folderPattern !== data.library_folder_pattern) {
    setFolderPattern(data.library_folder_pattern)
  }
  if (data && !filePatternDirty && filePattern !== data.file_naming_pattern) {
    setFilePattern(data.file_naming_pattern)
  }

  async function handleToggle(key: keyof AppSettings, value: boolean) {
    setSaving(key)
    setError(null)
    try {
      await updateSettings({ [key]: value })
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to update setting')
    } finally {
      setSaving(null)
    }
  }

  async function handleSaveFolderPattern() {
    setSaving('library_folder_pattern')
    setError(null)
    try {
      await updateSettings({ library_folder_pattern: folderPattern })
      setFolderPatternDirty(false)
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to update setting')
    } finally {
      setSaving(null)
    }
  }

  async function handleSaveFilePattern() {
    setSaving('file_naming_pattern')
    setError(null)
    try {
      await updateSettings({ file_naming_pattern: filePattern })
      setFilePatternDirty(false)
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to update setting')
    } finally {
      setSaving(null)
    }
  }

  if (!data && isFetching) {
    return (
      <div style={styles.page}>
        <h1 style={styles.heading}>Settings</h1>
        <div style={styles.loading}>Loading...</div>
      </div>
    )
  }

  return (
    <div style={styles.page}>
      <h1 style={styles.heading}>Settings</h1>

      {error && <div style={styles.error}>{error}</div>}

      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>User Access</h2>

        <Toggle
          label="Open Registration"
          description="Allow new users to create accounts. When disabled, only admins can create users from the Users page."
          checked={data?.registration_enabled ?? true}
          onChange={v => handleToggle('registration_enabled', v)}
          disabled={saving === 'registration_enabled'}
        />

        <Toggle
          label="Require Approval"
          description="New requests from non-admin users require admin approval before acquisition begins."
          checked={data?.require_approval ?? true}
          onChange={v => handleToggle('require_approval', v)}
          disabled={saving === 'require_approval'}
        />
      </section>

      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>Library</h2>

        <div style={styles.settingRow}>
          <div style={{ ...styles.settingText, flex: 1 }}>
            <div style={styles.settingLabel}>Folder Naming Pattern</div>
            <div style={styles.settingDesc}>
              How albums are organized in your music library. Variables: <code style={styles.code}>{'{artist}'}</code> <code style={styles.code}>{'{album}'}</code> <code style={styles.code}>{'{year}'}</code>
            </div>
            <div style={styles.inputRow}>
              <input
                style={styles.textInput}
                value={folderPattern}
                onChange={e => { setFolderPattern(e.target.value); setFolderPatternDirty(true) }}
                placeholder="{artist}/{album} [{year}]"
                disabled={saving === 'library_folder_pattern'}
              />
              {folderPatternDirty && (
                <button
                  style={styles.saveBtn}
                  onClick={handleSaveFolderPattern}
                  disabled={saving === 'library_folder_pattern'}
                >
                  {saving === 'library_folder_pattern' ? 'Saving...' : 'Save'}
                </button>
              )}
            </div>
            <div style={styles.previewText}>
              Preview: {folderPattern.replace('{artist}', 'Pink Floyd').replace('{album}', 'The Dark Side of the Moon').replace('{year}', '1973')}
            </div>
          </div>
        </div>

        <div style={styles.settingRow}>
          <div style={{ ...styles.settingText, flex: 1 }}>
            <div style={styles.settingLabel}>File Naming Pattern</div>
            <div style={styles.settingDesc}>
              How audio files are renamed when moved to your library. Variables: <code style={styles.code}>{'{track}'}</code> <code style={styles.code}>{'{artist}'}</code> <code style={styles.code}>{'{title}'}</code>
            </div>
            <div style={styles.inputRow}>
              <input
                style={styles.textInput}
                value={filePattern}
                onChange={e => { setFilePattern(e.target.value); setFilePatternDirty(true) }}
                placeholder="{track}-{artist}-{title}"
                disabled={saving === 'file_naming_pattern'}
              />
              {filePatternDirty && (
                <button
                  style={styles.saveBtn}
                  onClick={handleSaveFilePattern}
                  disabled={saving === 'file_naming_pattern'}
                >
                  {saving === 'file_naming_pattern' ? 'Saving...' : 'Save'}
                </button>
              )}
            </div>
            <div style={styles.previewText}>
              Preview: {filePattern.replace('{track}', '03').replace('{artist}', 'Pink Floyd').replace('{title}', 'Time')}.flac
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

const TOGGLE_W = 44
const TOGGLE_H = 24
const KNOB_SIZE = 18

const styles: Record<string, React.CSSProperties> = {
  page: {
    maxWidth: 700,
    margin: '0 auto',
    padding: '2rem 1rem',
  },
  heading: {
    fontSize: '1.75rem',
    fontWeight: 700,
    color: '#f0f0f0',
    margin: '0 0 1.5rem',
  },
  loading: {
    color: '#555',
    padding: '2rem',
  },
  error: {
    color: '#fca5a5',
    background: '#1a1a1a',
    border: '1px solid #7c3030',
    borderRadius: 8,
    padding: '0.75rem 1rem',
    marginBottom: '1.5rem',
    fontSize: '0.85rem',
  },
  section: {
    marginBottom: '2rem',
  },
  sectionTitle: {
    fontSize: '1rem',
    fontWeight: 600,
    color: '#999',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '1rem',
    paddingBottom: '0.5rem',
    borderBottom: '1px solid #222',
  },
  settingRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1.5rem',
    padding: '1rem',
    background: '#1a1a1a',
    border: '1px solid #2a2a2a',
    borderRadius: 8,
    marginBottom: '0.5rem',
  },
  settingText: {
    flex: 1,
  },
  settingLabel: {
    fontSize: '0.95rem',
    fontWeight: 600,
    color: '#e0e0e0',
  },
  settingDesc: {
    fontSize: '0.8rem',
    color: '#666',
    marginTop: '0.25rem',
    lineHeight: 1.4,
  },
  toggleOn: {
    width: TOGGLE_W,
    height: TOGGLE_H,
    borderRadius: TOGGLE_H / 2,
    border: 'none',
    background: '#2563eb',
    cursor: 'pointer',
    padding: 3,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexShrink: 0,
    transition: 'background 0.2s',
  },
  toggleOff: {
    width: TOGGLE_W,
    height: TOGGLE_H,
    borderRadius: TOGGLE_H / 2,
    border: 'none',
    background: '#333',
    cursor: 'pointer',
    padding: 3,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-start',
    flexShrink: 0,
    transition: 'background 0.2s',
  },
  toggleKnobOn: {
    width: KNOB_SIZE,
    height: KNOB_SIZE,
    borderRadius: '50%',
    background: '#fff',
    transition: 'all 0.2s',
  },
  toggleKnobOff: {
    width: KNOB_SIZE,
    height: KNOB_SIZE,
    borderRadius: '50%',
    background: '#888',
    transition: 'all 0.2s',
  },
  code: {
    background: '#2a2a2a',
    padding: '1px 5px',
    borderRadius: 4,
    fontSize: '0.8rem',
    color: '#93c5fd',
  },
  inputRow: {
    display: 'flex',
    gap: '0.5rem',
    alignItems: 'center',
    marginTop: '0.5rem',
  },
  textInput: {
    flex: 1,
    background: '#111',
    border: '1px solid #333',
    borderRadius: 6,
    padding: '0.5rem 0.75rem',
    color: '#e0e0e0',
    fontSize: '0.9rem',
    fontFamily: 'monospace',
    outline: 'none',
  },
  saveBtn: {
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    padding: '0.5rem 1rem',
    fontSize: '0.85rem',
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },
  previewText: {
    fontSize: '0.75rem',
    color: '#555',
    marginTop: '0.35rem',
    fontFamily: 'monospace',
  },
}
