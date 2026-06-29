import { useCallback, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { AccessibleModal } from './AccessibleModal'
import { restoredSnapshotError } from './restoreSync'
import { listDeckVersions, restoreDeckVersion } from '@/lib/api'
import type { DeckStatus, DeckVersion, OnlyOfficeEditorConfig } from '@/types'

interface VersionHistoryDialogProps {
  deckId: string
  currentVersionId: string
  open: boolean
  interactionsDisabled: boolean
  onClose: () => void
  onRestoringChange: (restoring: boolean) => void
  onRestored: (status: DeckStatus) => void
  onRestoreSyncError: (message: string, expected: DeckStatus) => void
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
  interactionsDisabled,
  onClose,
  onRestoringChange,
  onRestored,
  onRestoreSyncError,
}: VersionHistoryDialogProps) {
  const queryClient = useQueryClient()
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const [confirmation, setConfirmation] = useState<DeckVersion | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const versionsQuery = useQuery({
    queryKey: ['deck-versions', deckId],
    queryFn: () => listDeckVersions(deckId),
    enabled: open,
    retry: false,
  })
  const restoreMutation = useMutation({
    mutationFn: async (version: DeckVersion) => {
      const status = await restoreDeckVersion(deckId, version.id)
      try {
        await Promise.all([
          queryClient.refetchQueries({ queryKey: ['deck', deckId], exact: true }, { throwOnError: true }),
          queryClient.refetchQueries({ queryKey: ['editor-config', deckId], exact: true }, { throwOnError: true }),
          queryClient.refetchQueries({ queryKey: ['deck-status', deckId], exact: true }, { throwOnError: true }),
          queryClient.refetchQueries({ queryKey: ['deck-versions', deckId], exact: true }, { throwOnError: true }),
        ])
      } catch (error) {
        throw new RestoreSyncError(
          error instanceof Error ? error.message : 'Failed to refresh the restored deck',
          status,
        )
      }
      const freshStatus = queryClient.getQueryData<DeckStatus>(['deck-status', deckId])
      const freshConfig = queryClient.getQueryData<OnlyOfficeEditorConfig>(['editor-config', deckId])
      const error = restoredSnapshotError(deckId, status, freshStatus, freshConfig)
      if (error) throw new RestoreSyncError(error, status)
      return freshStatus ?? status
    },
    onMutate: () => {
      setRestoreError(null)
      onRestoringChange(true)
    },
    onSuccess: (status) => {
      onRestored(status)
      onRestoringChange(false)
      setConfirmation(null)
      setRestoreError(null)
      onClose()
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Failed to restore version'
      if (error instanceof RestoreSyncError) {
        onRestoreSyncError(message, error.expected)
      } else {
        onRestoringChange(false)
      }
      setRestoreError(message)
    },
  })

  const close = useCallback(() => {
    setConfirmation(null)
    setRestoreError(null)
    onClose()
  }, [onClose])

  if (!open) return null

  const versions = [...(versionsQuery.data?.versions ?? [])]
    .sort((left, right) => right.version_number - left.version_number)
  const queryError = versionsQuery.error instanceof Error
    ? versionsQuery.error.message
    : versionsQuery.error ? 'Failed to load version history' : null

  return (
    <AccessibleModal open={open} labelledBy="version-history-title" initialFocusRef={closeButtonRef} onRequestClose={close} canClose={!restoreMutation.isPending}>
      <div className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-5 text-slate-100 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 id="version-history-title" className="text-lg font-semibold">Version history</h2>
          <button ref={closeButtonRef} type="button" onClick={close} disabled={restoreMutation.isPending} aria-label="Close version history" className="rounded px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-white">×</button>
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
                  disabled={isCurrent || interactionsDisabled || restoreMutation.isPending}
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
                disabled={interactionsDisabled || restoreMutation.isPending}
                onClick={() => restoreMutation.mutate(confirmation)}
                aria-label={`Confirm restore version ${confirmation.version_number}`}
              >
                {restoreMutation.isPending ? 'Restoring…' : 'Confirm restore'}
              </Button>
            </div>
          </div>
        )}
        {restoreError && <p role="alert" className="mt-3 text-sm text-red-300">{restoreError}</p>}
      </div>
    </AccessibleModal>
  )
}

class RestoreSyncError extends Error {
  readonly expected: DeckStatus

  constructor(message: string, expected: DeckStatus) {
    super(message)
    this.expected = expected
  }
}
