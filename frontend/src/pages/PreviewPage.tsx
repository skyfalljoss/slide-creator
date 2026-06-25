import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { refine } from '@/lib/api'
import { useDeck } from '@/state/deck'
import { SlideBlocks } from '@/components/SlideBlocks'

const REFINE_OPTIONS = ['Shorter', 'More formal', 'Add data', 'Simplify']

export function PreviewPage() {
  const navigate = useNavigate()
  const { state, updateSlide } = useDeck()
  const [selectedSlide, setSelectedSlide] = useState(0)
  const [designOpen, setDesignOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const refineMutation = useMutation({ mutationFn: refine })

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
          <h2 className="text-2xl font-bold text-citi-dark">Preview & Refine</h2>
          <p className="text-slate-600 mt-1">Review your slides, edit bullets, or refine with AI.</p>
        </div>
        <Button onClick={() => navigate('/export')}>Export to PPTX</Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <div className="flex gap-2 overflow-x-auto pb-2 lg:block lg:space-y-2 lg:overflow-visible lg:pb-0">
          {state.slides.map((s, i) => (
            <button
              key={s.index}
              onClick={() => {
                setSelectedSlide(i)
                setDesignOpen(false)
              }}
              className={`min-w-48 lg:min-w-0 w-full text-left p-3 rounded-lg border text-sm transition-colors ${
                i === selectedSlide
                  ? 'border-citi-blue bg-citi-blue/5'
                  : 'border-slate-200 hover:border-slate-300'
              }`}
            >
              <div className="font-medium">{s.title}</div>
              <div className="text-xs text-slate-500 mt-0.5">{s.bullets.length} bullets</div>
            </button>
          ))}
        </div>

        <Card className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Slide {slide.index}: {slide.title}</h3>
            <span className="text-xs bg-citi-blue/10 text-citi-blue px-2 py-1 rounded">Slide {selectedSlide + 1}/{state.slides.length}</span>
          </div>

          <div className="aspect-video overflow-hidden rounded-xl border border-slate-200 bg-[#f7f8fb] p-5 shadow-inner">
            <div className="flex h-full flex-col bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">Strictly Private and Confidential</div>
                  {slide.kicker && <div className="mt-2 text-[11px] font-bold uppercase tracking-[0.16em] text-citi-red">{slide.kicker}</div>}
                  <h4 className="mt-2 max-w-3xl text-2xl font-bold leading-tight text-citi-dark">{slide.title}</h4>
                  {slide.subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-500">{slide.subtitle}</p>}
                  <div className="mt-3 h-1 w-16 bg-citi-red" />
                </div>
                <div className="text-right text-lg font-bold text-citi-blue">citi</div>
              </div>

              {slide.blocks && slide.blocks.length > 0 ? (
                <SlideBlocks blocks={slide.blocks} />
              ) : (
              <div className="mt-5 grid flex-1 gap-4 md:grid-cols-[0.95fr_1.05fr]">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-citi-blue">Key Messages</div>
                  <ul className="space-y-2">
                    {slide.bullets.map((b, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-citi-blue" />
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="rounded-lg border border-citi-blue/20 bg-white p-4">
                  {slide.chart_data ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-citi-blue">Chart: {slide.chart_data.title}</div>
                        <span className="rounded bg-citi-blue/10 px-2 py-1 text-[10px] font-semibold uppercase text-citi-blue">{slide.chart_data.type}</span>
                      </div>
                      <div className="flex h-24 items-end gap-2 border-b border-l border-slate-300 px-3">
                        {slide.chart_data.series[0]?.values.slice(0, 6).map((value, i) => (
                          <div
                            key={`${slide.chart_data?.series[0]?.name}-${i}`}
                            className="w-7 bg-citi-blue"
                            style={{ height: `${Math.max(18, Math.min(92, Number(value)))}%` }}
                            aria-label={`${slide.chart_data?.categories[i] ?? 'Category'} ${value}`}
                          />
                        ))}
                      </div>
                      {slide.chart_audit && (
                        <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                          <div>Source: {slide.chart_audit.source_filename}</div>
                          <div>{[slide.chart_audit.category_column, ...slide.chart_audit.value_columns].join(', ')}</div>
                          <div>{slide.chart_audit.row_count} rows, recommendation {slide.chart_audit.recommendation_status}</div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="flex h-full flex-col justify-between">
                      <div>
                        <div className="text-sm font-semibold text-citi-blue">Visual Treatment</div>
                        <p className="mt-2 text-sm text-slate-600">Citi-style callout panel for the slide's core message.</p>
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div className="h-14 rounded bg-citi-blue" />
                        <div className="h-14 rounded bg-citi-blue/15" />
                        <div className="h-14 rounded bg-citi-red/15" />
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
            <div className="rounded-lg border border-slate-200">
              <button
                type="button"
                aria-expanded={designOpen}
                onClick={() => setDesignOpen((open) => !open)}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium text-slate-700"
              >
                <span>Design direction</span>
                <span className="text-xs text-slate-500">{designOpen ? 'Hide' : 'Show'}</span>
              </button>
              {designOpen && <div className="border-t border-slate-200 px-3 py-2 text-sm text-slate-600">{slide.visual_direction}</div>}
            </div>
          )}

          {slide.notes && (
            <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
              <span className="font-medium text-slate-700">Speaker notes:</span> {slide.notes}
            </div>
          )}

          <div className="border-t pt-4 space-y-2">
            <div className="flex flex-wrap gap-2">
              {REFINE_OPTIONS.map((opt) => (
                <Button
                  key={opt}
                  variant="outline"
                  size="sm"
                  onClick={() => handleRefine(opt)}
                  disabled={refineMutation.isPending}
                >
                  {opt}
                </Button>
              ))}
            </div>
            {refineMutation.isPending && <p className="text-xs text-slate-500 animate-pulse">Refining slide...</p>}
            {error && <p className="text-xs text-citi-red">{error}</p>}
          </div>
        </Card>
      </div>
    </div>
  )
}
