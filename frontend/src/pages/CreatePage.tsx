import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card } from '@/components/ui/Card'
import type { DeckType } from '@/types'
import { generate, uploadFile } from '@/lib/api'
import { useDeck } from '@/state/deck'

type SourceType = 'brief' | 'script'
type Audience = 'corporate' | 'casual' | 'academic'
type Theme = 'minimalist' | 'bold' | 'dark'
type AspectRatio = '16:9' | '4:3'

const DECK_TYPES: { value: DeckType; label: string; desc: string }[] = [
  { value: 'sales_9', label: 'Sales / Client (9 slides)', desc: 'Title, Executive Summary, Situation, Solution, Deep Dive, Why Citi, Case Study, Next Steps' },
  { value: 'internal_6', label: 'Internal (6 slides)', desc: 'Title, Objective, Key Findings, Analysis, Recommendation, Risks/Appendix' },
]

const SOURCE_TYPES: { value: SourceType; label: string; desc: string }[] = [
  { value: 'brief', label: 'Describe a brief', desc: 'Tell SlideForge what you want and it writes the deck' },
  { value: 'script', label: 'Paste a script', desc: 'Paste a blog post, speech, or notes to convert into slides' },
]

const AUDIENCES: { value: Audience; label: string }[] = [
  { value: 'corporate', label: 'Corporate' },
  { value: 'casual', label: 'Casual' },
  { value: 'academic', label: 'Academic' },
]

const THEMES: { value: Theme; label: string; desc: string; swatch: string }[] = [
  { value: 'minimalist', label: 'Minimalist', desc: 'Clean white slides with Citi-blue accents', swatch: 'bg-white border-slate-300' },
  { value: 'bold', label: 'Bold', desc: 'Heavier accents and navy headers', swatch: 'bg-citi-blue border-citi-blue' },
  { value: 'dark', label: 'Dark Mode', desc: 'Dark navy background with light text', swatch: 'bg-slate-900 border-slate-900' },
]

const ASPECT_RATIOS: { value: AspectRatio; label: string; desc: string }[] = [
  { value: '16:9', label: '16:9 Widescreen', desc: 'Standard for modern displays' },
  { value: '4:3', label: '4:3 Standard', desc: 'Classic, for older projectors' },
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

  const uploadMutation = useMutation({ mutationFn: uploadFile })
  const generateMutation = useMutation({ mutationFn: generate })
  const working = uploadMutation.isPending || generateMutation.isPending

  const isScript = sourceType === 'script'
  const maxChars = isScript ? SCRIPT_MAX : BRIEF_MAX
  const promptLabel = isScript ? 'Paste your script, notes, or transcript' : 'Describe your presentation'
  const promptPlaceholder = isScript
    ? 'Paste a blog post, speech, meeting notes, or transcript. SlideForge will chunk it into slides...'
    : 'e.g., A pitch for a $500M syndicated loan facility for Acme Corp...'

  const handleGenerate = async () => {
    if (!prompt.trim()) return
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
        deckType,
        slides: result.slides,
        uploadedFile,
      })
      navigate('/preview')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate deck')
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-citi-dark">Create a New Deck</h2>
        <p className="text-slate-600 mt-1">Describe what you need or paste a source document, and SlideForge will generate a first draft.</p>
      </div>

      <Card className="p-6 space-y-6">
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Input mode</label>
          <div className="grid sm:grid-cols-2 gap-3">
            {SOURCE_TYPES.map((st) => (
              <button
                key={st.value}
                type="button"
                aria-pressed={sourceType === st.value}
                onClick={() => setSourceType(st.value)}
                className={`text-left p-4 rounded-lg border-2 transition-colors ${
                  sourceType === st.value ? 'border-citi-blue bg-citi-blue/5' : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="font-medium text-sm">{st.label}</div>
                <div className="text-xs text-slate-500 mt-1">{st.desc}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <label htmlFor="prompt" className="text-sm font-medium text-slate-700">
            {promptLabel}
          </label>
          <textarea
            id="prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={promptPlaceholder}
            maxLength={maxChars}
            rows={isScript ? 12 : 6}
            className="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-citi-blue/50 focus:border-citi-blue resize-y"
          />
          <p className="text-xs text-slate-400 text-right">{prompt.length}/{maxChars}</p>
        </div>

        <div className="space-y-2">
          <label htmlFor="audience" className="text-sm font-medium text-slate-700">Target audience</label>
          <select
            id="audience"
            value={audience}
            onChange={(e) => setAudience(e.target.value as Audience)}
            className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-citi-blue/50 focus:border-citi-blue"
          >
            {AUDIENCES.map((a) => (
              <option key={a.value} value={a.value}>{a.label}</option>
            ))}
          </select>
          <p className="text-xs text-slate-400">Sets the tone of the generated copy</p>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Visual theme</label>
          <div className="grid sm:grid-cols-3 gap-3">
            {THEMES.map((t) => (
              <button
                key={t.value}
                type="button"
                aria-pressed={theme === t.value}
                onClick={() => setTheme(t.value)}
                className={`text-left p-4 rounded-lg border-2 transition-colors ${
                  theme === t.value ? 'border-citi-blue bg-citi-blue/5' : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <span className={`inline-block w-6 h-6 rounded border ${t.swatch} mb-2`} aria-hidden="true" />
                <div className="font-medium text-sm">{t.label}</div>
                <div className="text-xs text-slate-500 mt-1">{t.desc}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Aspect ratio</label>
          <div className="grid sm:grid-cols-2 gap-3">
            {ASPECT_RATIOS.map((ar) => (
              <button
                key={ar.value}
                type="button"
                aria-pressed={aspectRatio === ar.value}
                onClick={() => setAspectRatio(ar.value)}
                className={`text-left p-4 rounded-lg border-2 transition-colors ${
                  aspectRatio === ar.value ? 'border-citi-blue bg-citi-blue/5' : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="font-medium text-sm">{ar.label}</div>
                <div className="text-xs text-slate-500 mt-1">{ar.desc}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Deck type</label>
          <div className="grid sm:grid-cols-2 gap-3">
            {DECK_TYPES.map((dt) => (
              <button
                key={dt.value}
                type="button"
                onClick={() => setDeckType(dt.value)}
                className={`text-left p-4 rounded-lg border-2 transition-colors ${
                  deckType === dt.value
                    ? 'border-citi-blue bg-citi-blue/5'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="font-medium text-sm">{dt.label}</div>
                <div className="text-xs text-slate-500 mt-1">{dt.desc}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <label htmlFor="file" className="text-sm font-medium text-slate-700">
            Data file (optional)
          </label>
          <Input
            id="file"
            type="file"
            accept=".xlsx,.csv"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <p className="text-xs text-slate-400">Upload Excel or CSV to auto-generate charts</p>
          {uploadMutation.data && (
            <p className="text-xs text-emerald-600">
              Uploaded {uploadMutation.data.filename}: {uploadMutation.data.row_count} rows
            </p>
          )}
        </div>

        {error && <p className="rounded-lg border border-citi-red/30 bg-citi-red/5 px-3 py-2 text-sm text-citi-red">{error}</p>}

        <Button size="lg" onClick={handleGenerate} disabled={!prompt.trim() || working}>
          {uploadMutation.isPending ? 'Uploading data...' : generateMutation.isPending ? 'Generating...' : 'Generate Deck'}
        </Button>
      </Card>
    </div>
  )
}
