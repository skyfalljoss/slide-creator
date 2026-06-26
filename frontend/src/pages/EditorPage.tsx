import { useRef, useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as fabric from 'fabric'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { getDeck, updateDeck, exportDeckById } from '@/lib/api'
import { slideToCanvasObjects, canvasObjectsToSlide, createEmptySlide } from '@/lib/canvas-bridge'
import type { SlideData } from '@/types'

export function EditorPage() {
  const { deckId } = useParams<{ deckId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const fabricRef = useRef<fabric.Canvas | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [deckName, setDeckName] = useState('')
  const [deckNameInitialized, setDeckNameInitialized] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDirty, setIsDirty] = useState(false)
  const [zoom, setZoom] = useState(1)
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data: deck, isLoading } = useQuery({
    queryKey: ['deck', deckId],
    queryFn: () => getDeck(deckId!),
    enabled: !!deckId,
  })

  if (deck && !deckNameInitialized) {
    setDeckName(deck.name)
    setDeckNameInitialized(true)
  }

  const saveMutation = useMutation({
    mutationFn: (data: { slides: SlideData[]; name?: string }) =>
      updateDeck(deckId!, { slides: data.slides, name: data.name }),
    onSuccess: () => setIsDirty(false),
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to save'),
  })

  const exportMutation = useMutation({
    mutationFn: () => exportDeckById(deckId!),
    onSuccess: (data) => window.open(data.download_url, '_blank'),
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to export'),
  })

  const persistSlides = useCallback((slides: SlideData[]) => {
    setIsDirty(true)
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(() => {
      saveMutation.mutate({ slides })
    }, 3000)
  }, [saveMutation])

  const renderSlide = useCallback((canvas: fabric.Canvas, slide: SlideData) => {
    canvas.clear()
    const objects = slideToCanvasObjects(slide, 960, 540, '#1E293B')

    for (const obj of objects) {
      if (obj.type === 'rect') {
        const rect = new fabric.Rect({
          left: obj.left || 0,
          top: obj.top || 0,
          width: obj.width || 960,
          height: obj.height || 540,
          fill: obj.fill || '#1E293B',
          selectable: obj.selectable !== false,
          evented: obj.evented !== false,
        })
        canvas.add(rect)
      } else if (obj.type === 'text') {
        const textbox = new fabric.Textbox(obj.text || '', {
          left: obj.left || 0,
          top: obj.top || 0,
          fontSize: obj.fontSize || 16,
          fontFamily: obj.fontFamily || 'Inter',
          fontWeight: Array.isArray(obj.fontWeight) ? obj.fontWeight[0] : obj.fontWeight || 'normal',
          fill: obj.fill || '#FFFFFF',
          width: (obj.width || 840) as number,
          editable: true,
        })
        canvas.add(textbox)
      }
    }
    canvas.renderAll()
  }, [])

  useEffect(() => {
    if (!canvasRef.current || !deck) return

    if (fabricRef.current) {
      fabricRef.current.dispose()
    }

    const canvas = new fabric.Canvas(canvasRef.current, {
      width: 960,
      height: 540,
      backgroundColor: '#0F172A',
      selection: true,
    })

    fabricRef.current = canvas

    canvas.on('object:modified', () => {
      const slides = deck.slides
      const currentSlide = slides[selectedIndex]
      if (!currentSlide) return
      const objects = canvas.getObjects().map((o) => o.toJSON())
      const updated = canvasObjectsToSlide(objects, currentSlide)
      const newSlides = [...slides]
      newSlides[selectedIndex] = updated
      persistSlides(newSlides)
    })

    if (deck.slides[selectedIndex]) {
      renderSlide(canvas, deck.slides[selectedIndex])
    }

    const resizeCanvas = () => {
      if (!canvasRef.current?.parentElement) return
      const parent = canvasRef.current.parentElement
      const scale = Math.min(
        (parent.clientWidth - 40) / 960,
        (parent.clientHeight - 40) / 540,
      )
      canvas.setZoom(scale)
      canvas.setWidth(960 * scale)
      canvas.setHeight(540 * scale)
      setZoom(Math.round(scale * 100))
    }
    resizeCanvas()
    window.addEventListener('resize', resizeCanvas)

    return () => {
      window.removeEventListener('resize', resizeCanvas)
      canvas.dispose()
      fabricRef.current = null
    }
  }, [deck, selectedIndex, renderSlide, persistSlides])

  if (!deckId) return <div className="text-white p-8">No deck ID provided</div>

  if (isLoading) {
    return <div className="flex items-center justify-center py-20"><div className="animate-pulse text-white text-lg">Loading deck...</div></div>
  }

  if (!deck) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <h2 className="text-xl text-white">Deck not found</h2>
        <Button variant="glow" className="mt-4" onClick={() => navigate('/my-decks')}>Back to My Decks</Button>
      </div>
    )
  }

  const slides = deck.slides
  const currentSlide = slides[selectedIndex] || slides[0]

  const handleSelectSlide = (index: number) => {
    if (fabricRef.current) {
      const objects = fabricRef.current.getObjects().map((o) => o.toJSON())
      const updated = canvasObjectsToSlide(objects, slides[selectedIndex])
      const newSlides = [...slides]
      newSlides[selectedIndex] = updated
      persistSlides(newSlides)
    }
    setSelectedIndex(index)
  }

  const handleAddSlide = () => {
    const newSlide = createEmptySlide(slides.length + 1)
    const newSlides = [...slides, newSlide]
    queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
    saveMutation.mutate({ slides: newSlides })
    setSelectedIndex(newSlides.length - 1)
  }

  const handleDeleteSlide = (index: number) => {
    if (slides.length <= 1) return
    const newSlides = slides.filter((_, i) => i !== index).map((s, i) => ({ ...s, index: i + 1 }))
    queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
    saveMutation.mutate({ slides: newSlides })
    setSelectedIndex(Math.min(index, newSlides.length - 1))
  }

  const handleSaveName = () => {
    if (deckName !== deck.name) {
      saveMutation.mutate({ slides, name: deckName })
    }
  }

  const setSlidesAndSchedule = (newSlides: SlideData[]) => {
    queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
    persistSlides(newSlides)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -mx-4 sm:-mx-6 lg:-mx-8 -mb-6">
      <div className="flex items-center justify-between px-4 py-2 bg-citi-dark border-b border-white/10 shrink-0">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/my-decks')} className="text-slate-400 hover:text-white text-sm">← Back</button>
          <input
            type="text"
            value={deckName}
            onChange={(e) => setDeckName(e.target.value)}
            onBlur={handleSaveName}
            onKeyDown={(e) => e.key === 'Enter' && handleSaveName()}
            className="bg-transparent text-white font-semibold text-sm border-none outline-none focus:ring-1 focus:ring-citi-blue rounded px-2 py-0.5"
          />
          <span className="text-xs text-slate-500">Slide {selectedIndex + 1} of {slides.length}</span>
          {isDirty && <span className="text-xs text-yellow-400">Unsaved changes</span>}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="border-white/15 bg-white/5 text-slate-200" onClick={handleSaveName}>Save</Button>
          <Button size="sm" variant="glow" onClick={() => exportMutation.mutate()} disabled={exportMutation.isPending}>
            {exportMutation.isPending ? 'Exporting...' : 'Export PPTX'}
          </Button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <div className="w-44 bg-citi-dark/50 border-r border-white/10 overflow-y-auto shrink-0">
          <div className="p-2">
            <div className="text-[10px] uppercase text-slate-500 font-semibold px-1 mb-2">Slides</div>
            {slides.map((slide, i) => (
              <button
                key={slide.index}
                onClick={() => handleSelectSlide(i)}
                className={cn(
                  'w-full text-left p-2 rounded mb-1 text-xs transition',
                  selectedIndex === i
                    ? 'bg-citi-blue/20 border border-citi-blue/50 text-white'
                    : 'border border-transparent text-slate-400 hover:bg-white/5 hover:text-white',
                )}
              >
                <div className="font-medium truncate">{slide.title}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">{slide.bullets.length} bullets</div>
              </button>
            ))}
            <button
              onClick={handleAddSlide}
              className="w-full mt-2 py-1.5 rounded text-xs font-medium bg-citi-blue/20 text-citi-blue hover:bg-citi-blue/30 transition"
            >
              + Add Slide
            </button>
          </div>
        </div>

        <div className="flex-1 bg-slate-700 flex items-center justify-center relative overflow-hidden">
          <div className="absolute top-2 left-1/2 -translate-x-1/2 flex items-center gap-1 bg-slate-800 rounded-lg px-2 py-1 z-10">
            <button onClick={() => {
              const c = fabricRef.current
              if (c) {
                const newZoom = (c.getZoom() || 1) * 0.8
                c.setZoom(newZoom)
                setZoom(Math.round(newZoom * 100))
              }
            }} className="text-white text-xs px-1">−</button>
            <span className="text-white text-xs px-1">{zoom}%</span>
            <button onClick={() => {
              const c = fabricRef.current
              if (c) {
                const newZoom = (c.getZoom() || 1) * 1.25
                c.setZoom(newZoom)
                setZoom(Math.round(newZoom * 100))
              }
            }} className="text-white text-xs px-1">+</button>
          </div>
          <div className="shadow-2xl">
            <canvas ref={canvasRef} />
          </div>
        </div>

        <div className="w-60 bg-citi-dark/50 border-l border-white/10 overflow-y-auto shrink-0 p-3">
          <div className="text-[10px] uppercase text-slate-500 font-semibold mb-3">Properties</div>

          {currentSlide && (
            <div className="space-y-3">
              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Title</label>
                <input
                  type="text"
                  value={currentSlide.title}
                  onChange={(e) => {
                    const newSlides = slides.map((s, i) =>
                      i === selectedIndex ? { ...s, title: e.target.value } : s,
                    )
                    setSlidesAndSchedule(newSlides)
                  }}
                  className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white"
                />
              </div>

              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Kicker</label>
                <input
                  type="text"
                  value={currentSlide.kicker || ''}
                  onChange={(e) => {
                    const newSlides = slides.map((s, i) =>
                      i === selectedIndex ? { ...s, kicker: e.target.value || null } : s,
                    )
                    setSlidesAndSchedule(newSlides)
                  }}
                  className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white"
                />
              </div>

              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Layout</label>
                <select
                  value={currentSlide.layout}
                  onChange={(e) => {
                    const newSlides = slides.map((s, i) =>
                      i === selectedIndex ? { ...s, layout: e.target.value } : s,
                    )
                    setSlidesAndSchedule(newSlides)
                  }}
                  className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white"
                >
                  <option value="title">Title</option>
                  <option value="content">Content</option>
                  <option value="chart">Chart</option>
                  <option value="next_steps">Next Steps</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Bullet Points</label>
                <div className="space-y-1">
                  {currentSlide.bullets.map((b, bi) => (
                    <input
                      key={bi}
                      type="text"
                      value={b}
                      onChange={(e) => {
                        const newBullets = [...currentSlide.bullets]
                        newBullets[bi] = e.target.value
                        const newSlides = slides.map((s, i) =>
                          i === selectedIndex ? { ...s, bullets: newBullets } : s,
                        )
                        setSlidesAndSchedule(newSlides)
                      }}
                      className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white"
                    />
                  ))}
                  <button
                    onClick={() => {
                      const newSlides = slides.map((s, i) =>
                        i === selectedIndex ? { ...s, bullets: [...s.bullets, ''] } : s,
                      )
                      setSlidesAndSchedule(newSlides)
                    }}
                    className="text-[10px] text-citi-blue hover:underline"
                  >
                    + Add bullet
                  </button>
                </div>
              </div>

              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Speaker Notes</label>
                <textarea
                  value={currentSlide.notes || ''}
                  onChange={(e) => {
                    const newSlides = slides.map((s, i) =>
                      i === selectedIndex ? { ...s, notes: e.target.value || '' } : s,
                    )
                    setSlidesAndSchedule(newSlides)
                  }}
                  rows={5}
                  className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white resize-none"
                />
              </div>

              {slides.length > 1 && (
                <button
                  onClick={() => handleDeleteSlide(selectedIndex)}
                  className="text-xs text-red-400 hover:text-red-300 mt-2"
                >
                  Delete this slide
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="absolute bottom-4 right-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-300 z-50">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">Dismiss</button>
        </div>
      )}
    </div>
  )
}
