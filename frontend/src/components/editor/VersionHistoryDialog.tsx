import { useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { listDeckVersions, restoreDeckVersion } from '@/lib/api'
import type { DeckStatus, DeckVersion } from '@/types'

interface VersionHistoryDialogProps {
  deckId: string
  currentVersionId: string
  open: boolean
  onClose: () => void
  onRestored: (status: DeckStatus) => void
}

function versionLabel(version: DeckVersion): string {
  if (version.source === 'generated') return 'Generated'
  if (version.source === 'restore') return 'Restored'
  return 'ONLYOFFICE save'
}

export function VersionHistoryDialog({
  deckId,
  currentVersionId,
  open,
  onClose,
  onRestored,
}: VersionHistoryDialogProps) {
  const queryClient = useQueryClient()
  const [confirmation, setConfirmation] = useState<DeckVersion | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const versionsQuery = useQuery({
    queryKey: ['deck-versions', deckId],
    queryFn: () => listDeckVersions(deckId),
    enabled: open,
    retry: false,
  })
  const restoreMutation = useMutation({
    mutationFn: (version: DeckVersion) => restoreDeckVersion(deckId, version.id),
    onSuccess: async (status) => {
      queryClient.setQueryData(['deck-status', deckId], status)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['deck', deckId] }),
        queryClient.invalidateQueries({ queryKey: ['editor-config', deckId] }),
        queryClient.invalidateQueries({ queryKey: ['deck-status', deckId] }),
        queryClient.invalidateQueries({ queryKey: ['deck-versions', deckId] }),
      ])
      onRestored(status)
      setConfirmation(null)
      setRestoreError(null)
      onClose()
    },
    onError: (error) => {
      setRestoreError(error instanceof Error ? error.message : 'Failed to restore version')
    },
  })

  const close = useCallback(() => {
    setConfirmation(null)
    setRestoreError(null)
    onClose()
  }, [onClose])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !restoreMutation.isPending) close()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [close, open, restoreMutation.isPending])

  if (!open) return null

  const versions = [...(versionsQuery.data?.versions ?? [])]
    .sort((left, right) => right.version_number - left.version_number)
  const queryError = versionsQuery.error instanceof Error
    ? versionsQuery.error.message
    : versionsQuery.error ? 'Failed to load version history' : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !restoreMutation.isPending) close()
    }}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="version-history-title"
        className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-5 text-slate-100 shadow-2xl"
      >
        <div className="flex items-center justify-between">
          <h2 id="version-history-title" className="text-lg font-semibold">Version history</h2>
          <button type="button" onClick={close} disabled={restoreMutation.isPending} aria-label="Close version history" className="rounded px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-white">×</button>
        </div>

        <div className="mt-4 max-h-[60vh] space-y-2 overflow-y-auto">
          {versionsQuery.isLoading && <p className="py-8 text-center text-sm text-slate-400">Loading versions…</p>}
          {queryError && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
              <p>{queryError}</p>
              <Button size="sm" className="mt-2" onClick={() => void versionsQuery.refetch()}>Retry</Button>
            </div>
          )}
          {!versionsQuery.isLoading && !queryError && versions.length === 0 && (
            <p className="py-8 text-center text-sm text-slate-400">No retained versions.</p>
          )}
          {versions.map((version) => {
            const isCurrent = version.id === currentVersionId
            return (
              <div key={version.id} data-testid="version-row" className="flex items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-800/70 p-3">
                <div className="min-w-0">
                  <p className="font-medium">Version {version.version_number}{isCurrent ? ' · Current' : ''}</p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {versionLabel(version)} · {new Date(version.created_at).toLocaleString()}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={isCurrent || restoreMutation.isPending}
                  onClick={() => {
                    setRestoreError(null)
                    setConfirmation(version)
                  }}
                  aria-label={`Restore version ${version.version_number}`}
                >
                  Restore
                </Button>
              </div>
            )
          })}
        </div>

        {confirmation && (
          <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
            <p>Restore version {confirmation.version_number} as a new current version?</p>
            <div className="mt-3 flex justify-end gap-2">
              <Button size="sm" variant="ghost" disabled={restoreMutation.isPending} onClick={() => setConfirmation(null)}>Cancel</Button>
              <Button
                size="sm"
                disabled={restoreMutation.isPending}
                onClick={() => restoreMutation.mutate(confirmation)}
                aria-label={`Confirm restore version ${confirmation.version_number}`}
              >
                {restoreMutation.isPending ? 'Restoring…' : 'Confirm restore'}
              </Button>
            </div>
          </div>
        )}
        {restoreError && <p role="alert" className="mt-3 text-sm text-red-300">{restoreError}</p>}
      </section>
    </div>
  )
}
