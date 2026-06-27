import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { refine, saveDeck, updateDeck } from '@/lib/api'
import { useDeck } from '@/state/deck'
import { SlideBlocks } from '@/components/SlideBlocks'

const REFINE_OPTIONS = ['Shorter', 'More formal', 'Add data', 'Simplify']

export function PreviewPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { state, updateSlide, markDeckSaved } = useDeck()
  const [selectedSlide, setSelectedSlide] = useState(0)
  const [designOpen, setDesignOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const refineMutation = useMutation({ mutationFn: refine })
  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name: state.slides[0]?.title || 'Untitled Deck',
        deck_type: state.deckType || 'sales_9',
        theme: 'minimalist',
        aspect_ratio: '16:9',
        slides: state.slides,
      }
      if (state.savedDeckId) {
        await updateDeck(state.savedDeckId, { name: payload.name, slides: payload.slides })
        return { id: state.savedDeckId, name: payload.name, created_at: '' }
      }
      const saved = await saveDeck(payload)
      markDeckSaved(saved.id)
      return saved
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['decks'] })
      navigate('/my-decks')
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to save deck'),
  })

  if (!state.sessionId || state.slides.length === 0) {
    return <Navigate to="/create" replace />
  }
  const sessionId = state.sessionId

  const slide = state.slides[Math.min(selectedSlide, state.slides.length - 1)]

  const handleRefine = async (instruction: string) => {
    setError(null)
    try {
      const result = await refineMutation.mutateAsync({
        session_id: sessionId,
        slide_index: slide.index,
        instruction,
      })
      updateSlide(result.slide)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refine slide')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-white">Preview &amp; Refine</h2>
          <p className="mt-1 text-slate-400">Review your slides, edit bullets, or refine with AI.</p>
        </div>
        <div className="flex gap-3">
          <Button
            variant="outline"
            className="border-white/15 bg-white/5 text-slate-200 hover:border-indigo-400/50 hover:bg-white/10"
            onClick={() => {
              saveMutation.mutate()
            }}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? 'Saving...' : state.savedDeckId ? 'Update in My Decks' : 'Save to My Decks'}
          </Button>
          <Button variant="glow" onClick={() => navigate('/export')}>Export to PPTX</Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        {/* Slide rail */}
        <div className="flex gap-2 overflow-x-auto pb-2 lg:block lg:space-y-2 lg:overflow-visible lg:pb-0">
          {state.slides.map((s, i) => {
            const active = i === selectedSlide
            return (
              <button
                key={s.index}
                onClick={() => {
                  setSelectedSlide(i)
                  setDesignOpen(false)
                }}
                aria-pressed={active}
                className={cn('tile min-w-48 w-full p-3 text-left text-sm lg:min-w-0', active && 'tile-active')}
              >
                <div className="font-medium text-slate-100">{s.title}</div>
                <div className="mt-0.5 text-xs text-slate-400">{s.bullets.length} bullets</div>
              </button>
            )
          })}
        </div>

        {/* Main panel */}
        <section className="glass-card space-y-4 p-6">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-white">Slide {slide.index}: {slide.title}</h3>
            <span className="rounded-md bg-indigo-400/15 px-2 py-1 text-xs font-medium text-indigo-200">
              Slide {selectedSlide + 1}/{state.slides.length}
            </span>
          </div>

          {/* Slide preview rendered in the app's dark theme */}
          <div className="aspect-video overflow-hidden rounded-xl border border-white/10 bg-space-950/60 p-4 shadow-inner">
            <div className="flex h-full flex-col rounded-md bg-gradient-to-br from-space-800 to-space-900 p-5 shadow-2xl ring-1 ring-white/10">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Strictly Private and Confidential</div>
                  {slide.kicker && <div className="mt-2 text-[11px] font-bold uppercase tracking-[0.16em] text-rose-400">{slide.kicker}</div>}
                  <h4 className="mt-2 max-w-3xl text-2xl font-bold leading-tight text-white">{slide.title}</h4>
                  {slide.subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-400">{slide.subtitle}</p>}
                  <div className="mt-3 h-1 w-16 bg-citi-red" />
                </div>
                <div className="text-right text-lg font-bold text-sky-400">citi</div>
              </div>

              {slide.blocks && slide.blocks.length > 0 ? (
                <SlideBlocks blocks={slide.blocks} />
              ) : (
              <div className="mt-5 grid flex-1 gap-4 md:grid-cols-[0.95fr_1.05fr]">
                <div className="rounded-lg border border-white/10 bg-white/[0.04] p-4">
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-sky-300">Key Messages</div>
                  <ul className="space-y-2">
                    {slide.bullets.map((b, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400" />
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="rounded-lg border border-white/10 bg-white/[0.04] p-4">
                  {slide.chart_data ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-sky-300">Chart: {slide.chart_data.title}</div>
                        <span className="rounded bg-sky-400/15 px-2 py-1 text-[10px] font-semibold uppercase text-sky-300">{slide.chart_data.type}</span>
                      </div>
                      <div className="flex h-24 items-end gap-2 border-b border-l border-white/15 px-3">
                        {slide.chart_data.series[0]?.values.slice(0, 6).map((value, i) => (
                          <div
                            key={`${slide.chart_data?.series[0]?.name}-${i}`}
                            className="w-7 bg-sky-400"
                            style={{ height: `${Math.max(18, Math.min(92, Number(value)))}%` }}
                            aria-label={`${slide.chart_data?.categories[i] ?? 'Category'} ${value}`}
                          />
                        ))}
                      </div>
                      {slide.chart_audit && (
                        <div className="rounded border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-slate-400">
                          <div>Source: {slide.chart_audit.source_filename}</div>
                          <div>{[slide.chart_audit.category_column, ...slide.chart_audit.value_columns].join(', ')}</div>
                          <div>{slide.chart_audit.row_count} rows, recommendation {slide.chart_audit.recommendation_status}</div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="flex h-full flex-col justify-between">
                      <div>
                        <div className="text-sm font-semibold text-sky-300">Visual Treatment</div>
                        <p className="mt-2 text-sm text-slate-300">Citi-style callout panel for the slide's core message.</p>
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div className="h-14 rounded bg-sky-500" />
                        <div className="h-14 rounded bg-sky-400/20" />
                        <div className="h-14 rounded bg-rose-400/20" />
                      </div>
                    </div>
                  )}
                </div>
              </div>
              )}

              <div className="mt-3 flex justify-between text-[10px] text-slate-500">
                <span>Confidential</span>
                <span>{slide.index} / {state.slides.length}</span>
              </div>
            </div>
          </div>

          {slide.visual_direction && (
            <div className="rounded-lg border border-white/10 bg-white/[0.03]">
              <button
                type="button"
                aria-expanded={designOpen}
                onClick={() => setDesignOpen((open) => !open)}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium text-slate-200"
              >
                <span>Design direction</span>
                <span className="text-xs text-indigo-300">{designOpen ? 'Hide' : 'Show'}</span>
              </button>
              {designOpen && <div className="border-t border-white/10 px-3 py-2 text-sm text-slate-300">{slide.visual_direction}</div>}
            </div>
          )}

          {slide.notes && (
            <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-300">
              <span className="font-medium text-slate-100">Speaker notes:</span> {slide.notes}
            </div>
          )}

          <div className="space-y-2 border-t border-white/10 pt-4">
            <div className="flex flex-wrap gap-2">
              {REFINE_OPTIONS.map((opt) => (
                <Button
                  key={opt}
                  variant="outline"
                  size="sm"
                  onClick={() => handleRefine(opt)}
                  disabled={refineMutation.isPending}
                  className="border-white/15 bg-white/5 text-slate-200 hover:border-indigo-400/50 hover:bg-white/10"
                >
                  {opt}
                </Button>
              ))}
            </div>
            {refineMutation.isPending && <p className="animate-pulse text-xs text-indigo-300">Refining slide...</p>}
            {error && <p className="text-xs text-rose-300">{error}</p>}
          </div>
        </section>
      </div>
    </div>
  )
}
