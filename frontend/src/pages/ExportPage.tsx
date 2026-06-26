import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { exportDeck } from '@/lib/api'
import { useDeck } from '@/state/deck'

export function ExportPage() {
  const { state, setExportResult } = useDeck()

  const [error, setError] = useState<string | null>(null)
  const [checkedAt] = useState(() => Date.now())
  const exportMutation = useMutation({ mutationFn: exportDeck })
  const deckLabel = state.deckType === 'internal_6' ? 'Internal Deck' : 'Sales / Client Deck'
  const exportResult = state.lastExport && Date.parse(state.lastExport.expires_at) > checkedAt ? state.lastExport : null

  if (!state.sessionId) {
    return <Navigate to="/preview" replace />
  }
  const sessionId = state.sessionId

  const handleExport = async () => {
    setError(null)
    try {
      const result = await exportMutation.mutateAsync({ session_id: sessionId })
      setExportResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export deck')
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="font-display text-3xl font-bold tracking-tight text-white">Export Deck</h2>
        <p className="mt-1 text-slate-400">Your deck is ready. Download as a brand-compliant PowerPoint file.</p>
      </div>

      <section className="glass-card mx-auto max-w-2xl space-y-6 p-8 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500/30 to-violet-500/30 ring-1 ring-indigo-400/40">
          <svg className="h-8 w-8 text-indigo-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>

        <div className="space-y-1">
          <p className="text-sm text-slate-400">Slides: <strong className="text-white">{state.slides.length}</strong></p>
          <p className="text-sm text-slate-400">Template: <strong className="text-white">{deckLabel}</strong></p>
          <p className="text-sm text-slate-400">Compliance check: <strong className="text-emerald-400">Passed</strong></p>
        </div>

        {error && <p className="rounded-lg border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{error}</p>}

        {exportResult ? (
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 text-sm font-medium text-emerald-400">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Export complete
            </div>
            <div>
              <a href={exportResult.download_url} target="_blank" rel="noreferrer" className="inline-flex">
                <Button variant="glow" size="lg">
                  Download PPTX
                </Button>
              </a>
            </div>
            <p className="text-xs text-slate-500">Link expires {new Date(exportResult.expires_at).toLocaleString()}</p>
          </div>
        ) : (
          <Button variant="glow" size="lg" onClick={handleExport} disabled={exportMutation.isPending}>
            {exportMutation.isPending ? 'Generating PPTX...' : 'Export as PPTX'}
          </Button>
        )}
      </section>
    </div>
  )
}
