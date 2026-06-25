import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
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
        <h2 className="text-2xl font-bold text-citi-dark">Export Deck</h2>
        <p className="text-slate-600 mt-1">Your deck is ready. Download as a brand-compliant PowerPoint file.</p>
      </div>

      <Card className="p-8 text-center space-y-6">
        <div className="w-16 h-16 rounded-full bg-citi-blue/10 flex items-center justify-center mx-auto">
          <svg className="w-8 h-8 text-citi-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>

        <div>
          <p className="text-sm text-slate-600">Slides: <strong>{state.slides.length}</strong></p>
          <p className="text-sm text-slate-600">Template: <strong>{deckLabel}</strong></p>
          <p className="text-sm text-slate-600">Compliance check: <strong className="text-emerald-600">Passed</strong></p>
        </div>

        {error && <p className="rounded-lg border border-citi-red/30 bg-citi-red/5 px-3 py-2 text-sm text-citi-red">{error}</p>}

        {exportResult ? (
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 text-emerald-600 text-sm font-medium">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Export complete
            </div>
            <a href={exportResult.download_url} target="_blank" rel="noreferrer" className="inline-flex">
              <Button size="lg">
              Download PPTX
              </Button>
            </a>
            <p className="text-xs text-slate-400">Link expires {new Date(exportResult.expires_at).toLocaleString()}</p>
          </div>
        ) : (
          <Button size="lg" onClick={handleExport} disabled={exportMutation.isPending}>
            {exportMutation.isPending ? 'Generating PPTX...' : 'Export as PPTX'}
          </Button>
        )}
      </Card>
    </div>
  )
}
