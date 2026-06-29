import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { GenerationOverlay } from '@/components/create/GenerationOverlay'
import { cn } from '@/lib/utils'
import type { DeckType } from '@/types'
import { generate, uploadFile } from '@/lib/api'
import { useDeck } from '@/state/deck'

type SourceType = 'brief' | 'script'
type Audience = 'corporate' | 'casual' | 'academic'
type Theme = 'minimalist' | 'bold' | 'dark'
type AspectRatio = '16:9' | '4:3'

type IconProps = { className?: string }

const DECK_TYPES: { value: DeckType; label: string; count: string }[] = [
  { value: 'sales_9', label: 'Sales / Client', count: '10+ slides' },
  { value: 'internal_6', label: 'Internal', count: '7+ slides' },
]

const SOURCE_TYPES: {
  value: SourceType
  label: string
  desc: string
  icon: (p: IconProps) => React.JSX.Element
}[] = [
  {
    value: 'brief',
    label: 'AI Brief',
    desc: 'Describe your vision and let AI structure the deck',
    icon: IconSparkles,
  },
  {
    value: 'script',
    label: 'Paste Script/Docs',
    desc: 'Paste your notes and let AI structure the deck',
    icon: IconDoc,
  },
]

const AUDIENCES: { value: Audience; label: string }[] = [
  { value: 'corporate', label: 'Corporate' },
  { value: 'casual', label: 'Casual' },
  { value: 'academic', label: 'Academic' },
]

const THEMES: { value: Theme; label: string; thumb: string }[] = [
  {
    value: 'minimalist',
    label: 'Minimalist',
    thumb:
      'linear-gradient(160deg, #1e3a5f 0%, #2d5a8c 45%, #6ea8d8 100%)',
  },
  {
    value: 'bold',
    label: 'Bold',
    thumb:
      'linear-gradient(120deg, #f97316 0%, #ec4899 45%, #8b5cf6 100%)',
  },
  {
    value: 'dark',
    label: 'Dark Mode',
    thumb:
      'radial-gradient(circle at 50% 45%, rgba(99,102,241,0.55), rgba(2,6,23,0.2) 38%, #020617 70%)',
  },
]

const ASPECT_RATIOS: { value: AspectRatio; label: string; wide: boolean }[] = [
  { value: '16:9', label: '16:9 Widescreen', wide: true },
  { value: '4:3', label: '4:3 Standard', wide: false },
]

const SCRIPT_MAX = 50000
const BRIEF_MAX = 5000

export function CreatePage() {
  const navigate = useNavigate()
  const deck = useDeck()
  const [prompt, setPrompt] = useState('')
  const [deckType, setDeckType] = useState<DeckType>('sales_9')
  const [sourceType, setSourceType] = useState<SourceType>('brief')
  const [audience, setAudience] = useState<Audience>('corporate')
  const [theme, setTheme] = useState<Theme>('minimalist')
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>('16:9')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [generationInFlight, setGenerationInFlight] = useState(false)
  const generationInFlightRef = useRef(false)

  const uploadMutation = useMutation({ mutationFn: uploadFile })
  const generateMutation = useMutation({ mutationFn: generate })
  const working = generationInFlight || uploadMutation.isPending || generateMutation.isPending

  const isScript = sourceType === 'script'
  const maxChars = isScript ? SCRIPT_MAX : BRIEF_MAX
  const promptLabel = isScript ? 'Paste your script, notes, or transcript' : 'Describe your presentation'
  const promptPlaceholder = isScript
    ? 'Paste a blog post, speech, meeting notes, or transcript. SlideForge will chunk it into slides...'
    : 'e.g., A pitch for a $500M syndicated loan facility for Acme Corp...'

  const handleGenerate = async () => {
    if (!prompt.trim() || generationInFlightRef.current) return
    generationInFlightRef.current = true
    setGenerationInFlight(true)
    setError(null)
    try {
      const uploadedFile = file ? await uploadMutation.mutateAsync(file) : null
      const result = await generateMutation.mutateAsync({
        prompt: prompt.trim(),
        deck_type: deckType,
        source_type: sourceType,
        target_audience: audience,
        theme,
        aspect_ratio: aspectRatio,
        file_id: uploadedFile?.file_id ?? null,
      })
      deck.setGeneratedDeck({
        sessionId: result.session_id,
        savedDeckId: result.deck_id,
        deckType,
        slides: result.slides,
        uploadedFile,
      })
      navigate(result.editor_path)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate deck')
    } finally {
      generationInFlightRef.current = false
      setGenerationInFlight(false)
    }
  }

  return (
    <div className="space-y-8">
      <GenerationOverlay key={working ? 'generating' : 'idle'} active={working} uploading={uploadMutation.isPending} />

      {/* Heading */}
      <header className="text-center">
        <h1 className="font-display text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
          Create a New Deck{' '}
          <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-sky-400 bg-clip-text text-transparent">
            - V2
          </span>
        </h1>
        <p className="mt-3 text-base text-slate-400">
          Describe your vision, select your style, and let AI forge your presentation.
        </p>
      </header>

      {/* Top row: Input mode + Describe */}
      <div className="grid gap-5 lg:grid-cols-3">
        <section className="glass-card p-5 lg:col-span-1">
          <SectionTitle>Input mode</SectionTitle>
          <div className="mt-3 grid grid-cols-2 gap-3">
            {SOURCE_TYPES.map((st) => {
              const Icon = st.icon
              const active = sourceType === st.value
              return (
                <button
                  key={st.value}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setSourceType(st.value)}
                  className={cn('tile flex flex-col items-center px-3 py-4 text-center', active && 'tile-active')}
                >
                  <Icon className={cn('h-7 w-7', active ? 'text-indigo-300' : 'text-slate-400')} />
                  <span className="mt-2 text-sm font-semibold text-slate-100">{st.label}</span>
                  <span className="mt-1 text-[11px] leading-snug text-slate-400">{st.desc}</span>
                </button>
              )
            })}
          </div>
        </section>

        <section className="glass-card flex flex-col p-5 lg:col-span-2">
          <SectionTitle>{promptLabel}</SectionTitle>
          <div className="relative mt-3 flex-1">
            <textarea
              id="prompt"
              aria-label={promptLabel}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={promptPlaceholder}
              maxLength={maxChars}
              className="field h-full min-h-[150px] w-full resize-y px-4 py-3 text-sm"
            />
          </div>
          <p className="mt-2 text-right text-xs text-slate-500">
            {prompt.length}/{maxChars}
          </p>
        </section>
      </div>

      {/* Bento row */}
      <div className="grid gap-5 lg:grid-cols-3">
        {/* Column 1: audience + aspect ratio */}
        <div className="flex flex-col gap-5">
          <section className="glass-card p-5">
            <SectionTitle>Target audience</SectionTitle>
            <div className="relative mt-3">
              <IconFlag className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-indigo-300" />
              <select
                id="audience"
                aria-label="Target audience"
                value={audience}
                onChange={(e) => setAudience(e.target.value as Audience)}
                className="field w-full appearance-none py-2.5 pl-9 pr-9 text-sm"
              >
                {AUDIENCES.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
              <IconChevron className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            </div>
          </section>

          <section className="glass-card p-5">
            <SectionTitle>Aspect ratio</SectionTitle>
            <div className="mt-3 grid grid-cols-2 gap-3">
              {ASPECT_RATIOS.map((ar) => {
                const active = aspectRatio === ar.value
                return (
                  <button
                    key={ar.value}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setAspectRatio(ar.value)}
                    className={cn('tile flex flex-col items-center px-3 py-4', active && 'tile-active')}
                  >
                    <span
                      className={cn(
                        'flex items-center justify-center rounded-md border',
                        active ? 'border-indigo-400/80' : 'border-slate-500/60',
                        ar.wide ? 'h-7 w-12' : 'h-8 w-10',
                      )}
                    >
                      <span className={cn('block rounded-sm', active ? 'bg-indigo-400/70' : 'bg-slate-500/60', ar.wide ? 'h-3 w-7' : 'h-4 w-6')} />
                    </span>
                    <span className="mt-2 text-xs font-semibold text-slate-100">{ar.label}</span>
                  </button>
                )
              })}
            </div>
          </section>
        </div>

        {/* Column 2: visual theme */}
        <section className="glass-card p-5">
          <SectionTitle>Visual theme</SectionTitle>
          <div className="mt-3 grid grid-cols-3 gap-3">
            {THEMES.map((t) => {
              const active = theme === t.value
              return (
                <button
                  key={t.value}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setTheme(t.value)}
                  className={cn('tile overflow-hidden p-1.5', active && 'tile-active')}
                >
                  <span className="block h-16 w-full rounded-md" style={{ backgroundImage: t.thumb }} aria-hidden="true" />
                  <span className="mt-2 block text-center text-xs font-semibold text-slate-100">{t.label}</span>
                </button>
              )
            })}
          </div>
        </section>

        {/* Column 3: deck type + data file */}
        <div className="flex flex-col gap-5">
          <section className="glass-card p-5">
            <SectionTitle>Deck type</SectionTitle>
            <div className="mt-3 grid grid-cols-2 gap-3">
              {DECK_TYPES.map((dt) => {
                const active = deckType === dt.value
                const Icon = dt.value === 'sales_9' ? IconUsers : IconChecklist
                return (
                  <button
                    key={dt.value}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setDeckType(dt.value)}
                    className={cn('tile flex flex-col items-center px-3 py-4 text-center', active && 'tile-active')}
                  >
                    <Icon className={cn('h-7 w-7', active ? 'text-indigo-300' : 'text-slate-400')} />
                    <span className="mt-2 text-sm font-semibold text-slate-100">{dt.label}</span>
                    <span className="mt-0.5 text-[11px] text-slate-400">({dt.count})</span>
                  </button>
                )
              })}
            </div>
          </section>

          <section className="glass-card p-5">
            <SectionTitle>Data file</SectionTitle>
            <label
              htmlFor="file"
              className="tile mt-3 flex cursor-pointer items-center justify-center gap-2 px-4 py-3 text-sm font-medium text-slate-200"
            >
              <IconUpload className="h-4 w-4 text-slate-300" />
              {file ? file.name : 'File upload'}
            </label>
            <input
              id="file"
              type="file"
              aria-label="Data file"
              accept=".xlsx,.csv"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="sr-only"
            />
            {uploadMutation.data && (
              <p className="mt-2 text-xs text-emerald-400">
                Uploaded {uploadMutation.data.filename}: {uploadMutation.data.row_count} rows
              </p>
            )}
          </section>
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-rose-400/40 bg-rose-500/10 px-4 py-2.5 text-sm text-rose-300">
          {error}
        </p>
      )}

      {/* Generate CTA */}
      <div className="flex justify-center pt-2">
        <Button
          variant="glow"
          size="lg"
          onClick={handleGenerate}
          disabled={!prompt.trim() || working}
          className={cn('h-14 w-full max-w-md text-lg', !working && prompt.trim() && 'animate-pulse-glow')}
        >
          {uploadMutation.isPending ? 'Uploading data...' : generateMutation.isPending ? 'Generating...' : 'Generate Deck'}
        </Button>
      </div>
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-semibold text-slate-200">{children}</h2>
}

/* --- Inline icons --- */

function IconSparkles({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z" />
      <path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8z" />
    </svg>
  )
}

function IconDoc({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h6" />
    </svg>
  )
}

function IconFlag({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M4 21V4M4 4h11l-1.5 4L16 12H4" />
    </svg>
  )
}

function IconChevron({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="m6 9 6 6 6-6" />
    </svg>
  )
}

function IconUsers({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <circle cx="9" cy="8" r="3" />
      <path d="M3 20a6 6 0 0 1 12 0" />
      <path d="M16 6a3 3 0 0 1 0 6M21 20a6 6 0 0 0-4-5.6" />
    </svg>
  )
}

function IconChecklist({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="m3 7 1.5 1.5L7 6" />
      <path d="m3 16 1.5 1.5L7 15" />
      <path d="M11 7h10M11 16h10" />
    </svg>
  )
}

function IconUpload({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M12 16V4M7 9l5-5 5 5" />
      <path d="M5 20h14" />
    </svg>
  )
}
