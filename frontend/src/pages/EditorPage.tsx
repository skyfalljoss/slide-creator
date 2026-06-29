import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useBlocker, useNavigate, useParams } from 'react-router-dom'
import { AccessibleModal } from '@/components/editor/AccessibleModal'
import { OnlyOfficeEditor } from '@/components/editor/OnlyOfficeEditor'
import { restoredSnapshotError } from '@/components/editor/restoreSync'
import { VersionHistoryDialog } from '@/components/editor/VersionHistoryDialog'
import { Button } from '@/components/ui/Button'
import {
  deckDownloadUrl,
  getDeck,
  getDeckStatus,
  getEditorConfig,
  renameDeck,
} from '@/lib/api'
import type { DeckStatus, OnlyOfficeEditorConfig } from '@/types'

type SaveState =
  | { kind: 'clean' }
  | { kind: 'dirty'; baselineVersion: number }
  | { kind: 'pending'; baselineVersion: number }
  | { kind: 'confirmed'; version: number }
  | { kind: 'error'; message: string }

function queryErrorMessage(errors: unknown[]): string | null {
  const error = errors.find(Boolean)
  if (!error) return null
  return error instanceof Error ? error.message : 'Unable to open this deck'
}

export function EditorPage() {
  const { deckId } = useParams<{ deckId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [deckNameDraft, setDeckNameDraft] = useState<{ deckId: string; value: string } | null>(null)
  const [renameError, setRenameError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<SaveState>({ kind: 'clean' })
  const [editorError, setEditorError] = useState<string | null>(null)
  const [editorAttempt, setEditorAttempt] = useState(0)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [isRestoring, setIsRestoring] = useState(false)
  const [restoreSyncError, setRestoreSyncError] = useState<{ expected: DeckStatus; message: string } | null>(null)
  const [isSyncRetrying, setIsSyncRetrying] = useState(false)
  const cancelRenameRef = useRef(false)
  const renameSubmissionRef = useRef<string | null>(null)

  const deckQuery = useQuery({
    queryKey: ['deck', deckId],
    queryFn: () => getDeck(deckId!),
    enabled: Boolean(deckId),
    retry: false,
  })
  const configQuery = useQuery({
    queryKey: ['editor-config', deckId],
    queryFn: () => getEditorConfig(deckId!),
    enabled: Boolean(deckId),
    retry: false,
  })
  const statusQuery = useQuery({
    queryKey: ['deck-status', deckId],
    queryFn: () => getDeckStatus(deckId!),
    enabled: Boolean(deckId),
    retry: false,
  })
  const refetchStatus = statusQuery.refetch

  useEffect(() => {
    if (saveState.kind !== 'pending') return
    let cancelled = false
    let pollTimer: number | undefined
    const poll = async () => {
      const result = await refetchStatus()
      if (cancelled) return
      if (result.error) {
        setSaveState({
          kind: 'error',
          message: result.error instanceof Error ? result.error.message : 'Save confirmation failed',
        })
        return
      }
      if (result.data && result.data.current_version_number > saveState.baselineVersion) {
        setSaveState({ kind: 'confirmed', version: result.data.current_version_number })
        return
      }
      pollTimer = window.setTimeout(poll, 1_000)
    }
    pollTimer = window.setTimeout(poll, 1_000)
    const deadlineTimer = window.setTimeout(() => {
      cancelled = true
      if (pollTimer !== undefined) window.clearTimeout(pollTimer)
      setSaveState({ kind: 'error', message: 'Save confirmation timed out' })
    }, 30_000)
    return () => {
      cancelled = true
      if (pollTimer !== undefined) window.clearTimeout(pollTimer)
      window.clearTimeout(deadlineTimer)
    }
  }, [refetchStatus, saveState])

  const navigationBlocked = saveState.kind === 'dirty'
    || saveState.kind === 'pending'
    || saveState.kind === 'error'
    || isRestoring
  useEffect(() => {
    if (!navigationBlocked) return
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [navigationBlocked])
  const blocker = useBlocker(navigationBlocked)

  const renameMutation = useMutation({
    mutationFn: (name: string) => renameDeck(deckId!, name),
    onSuccess: (updatedDeck) => {
      queryClient.setQueryData(['deck', deckId], updatedDeck)
      setDeckNameDraft({ deckId: deckId!, value: updatedDeck.name })
      setRenameError(null)
      renameSubmissionRef.current = null
    },
    onError: (error) => {
      setRenameError(error instanceof Error ? error.message : 'Failed to rename deck')
      renameSubmissionRef.current = null
    },
  })

  const saveName = () => {
    if (cancelRenameRef.current) {
      cancelRenameRef.current = false
      return
    }
    if (!deckQuery.data || renameMutation.isPending) return
    const normalized = deckName.trim()
    if (!normalized) {
      setDeckNameDraft({ deckId: deckQuery.data.id, value: deckQuery.data.name })
      setRenameError('Deck name is required')
      return
    }
    if (normalized === deckQuery.data.name) {
      setDeckNameDraft({ deckId: deckQuery.data.id, value: normalized })
      return
    }
    if (renameSubmissionRef.current === normalized) return
    renameSubmissionRef.current = normalized
    renameMutation.mutate(normalized)
  }

  const handleDirtyChange = useCallback((dirty: boolean) => {
    const observedVersion = queryClient.getQueryData<{ current_version_number: number }>(
      ['deck-status', deckId],
    )?.current_version_number ?? 0
    if (dirty) {
      setSaveState((current) => {
        if (current.kind === 'dirty') return current
        if (current.kind === 'pending' && observedVersion <= current.baselineVersion) {
          return { kind: 'dirty', baselineVersion: current.baselineVersion + 1 }
        }
        return { kind: 'dirty', baselineVersion: observedVersion }
      })
      return
    }
    setSaveState((current) => {
      if (current.kind !== 'dirty') return current
      if (observedVersion > current.baselineVersion) {
        return { kind: 'confirmed', version: observedVersion }
      }
      return {
        kind: 'pending',
        baselineVersion: current.baselineVersion,
      }
    })
  }, [deckId, queryClient])

  const handleEditorError = useCallback((message: string) => {
    setEditorError(message)
  }, [])

  const requestBack = () => {
    navigate('/my-decks')
  }

  const retryRestoreSynchronization = () => {
    if (!deckId || !restoreSyncError) return
    const expected = restoreSyncError.expected
    setIsSyncRetrying(true)
    void Promise.all([
      queryClient.refetchQueries({ queryKey: ['deck', deckId], exact: true, type: 'all' }, { throwOnError: true }),
      queryClient.refetchQueries({ queryKey: ['editor-config', deckId], exact: true, type: 'all' }, { throwOnError: true }),
      queryClient.refetchQueries({ queryKey: ['deck-status', deckId], exact: true, type: 'all' }, { throwOnError: true }),
      queryClient.refetchQueries({ queryKey: ['deck-versions', deckId], exact: true, type: 'all' }, { throwOnError: true }),
    ]).then(() => {
      const freshStatus = queryClient.getQueryData<DeckStatus>(['deck-status', deckId])
      const freshConfig = queryClient.getQueryData<OnlyOfficeEditorConfig>(['editor-config', deckId])
      const error = restoredSnapshotError(deckId, expected, freshStatus, freshConfig)
      if (error) {
        setRestoreSyncError({ expected, message: error })
        return
      }
      setRestoreSyncError(null)
      setSaveState({ kind: 'confirmed', version: freshStatus!.current_version_number })
      setIsRestoring(false)
    }).catch((error: unknown) => {
      setRestoreSyncError({
        expected,
        message: error instanceof Error ? error.message : 'Failed to synchronize the restored editor',
      })
    }).finally(() => {
      setIsSyncRetrying(false)
    })
  }

  const discardDialog = (
    <DiscardChangesDialog
      open={blocker.state === 'blocked'}
      onCancel={() => {
        if (blocker.state === 'blocked') blocker.reset()
      }}
      onDiscard={() => {
        if (blocker.state === 'blocked') blocker.proceed()
      }}
    />
  )

  if (!deckId) {
    return <FailureView message="No deck ID was provided" onBack={() => navigate('/my-decks')} />
  }

  const loading = deckQuery.isLoading || configQuery.isLoading || statusQuery.isLoading
  if (loading) {
    return <div className="grid h-screen place-items-center bg-slate-950 text-sm text-slate-300">Loading editor…</div>
  }

  const requestError = queryErrorMessage([deckQuery.error, configQuery.error, statusQuery.error])
  if (!deckQuery.data || !configQuery.data || !statusQuery.data) {
    return (
      <>
        <FailureView
          message={requestError ?? 'Unable to open this deck'}
          onBack={requestBack}
          onRetry={() => {
            void Promise.all([deckQuery.refetch(), configQuery.refetch(), statusQuery.refetch()])
          }}
        />
        {discardDialog}
      </>
    )
  }

  if (requestError && !isRestoring) {
    return (
      <>
        <FailureView
          message={requestError}
          onBack={requestBack}
          onRetry={() => void Promise.all([deckQuery.refetch(), configQuery.refetch(), statusQuery.refetch()])}
        />
        {discardDialog}
      </>
    )
  }

  if (editorError) {
    return (
      <>
        <FailureView
          message={editorError}
          onBack={requestBack}
          onRetry={() => {
            setEditorError(null)
            setEditorAttempt((attempt) => attempt + 1)
          }}
        />
        {discardDialog}
      </>
    )
  }

  const currentStatus = statusQuery.data
  const deckName = deckNameDraft?.deckId === deckId ? deckNameDraft.value : deckQuery.data.name
  const statusText = saveState.kind === 'dirty'
    ? 'Unsaved'
    : saveState.kind === 'pending'
      ? 'Saving…'
      : saveState.kind === 'confirmed'
        ? `Saved as version ${saveState.version}`
        : saveState.kind === 'error'
          ? saveState.message
          : `Saved as version ${currentStatus.current_version_number}`

  return (
    <div className="h-screen overflow-hidden bg-slate-950 text-slate-100">
      <header className="flex h-12 items-center justify-between gap-3 overflow-x-auto border-b border-slate-700 bg-slate-900 px-3">
        <div className="flex min-w-[20rem] flex-1 items-center gap-2 sm:gap-3">
          <button type="button" onClick={requestBack} className="shrink-0 rounded px-2 py-1 text-sm text-slate-300 hover:bg-slate-800 hover:text-white">← Back</button>
          <input
            aria-label="Deck name"
            value={deckName}
            maxLength={500}
            disabled={renameMutation.isPending}
            onChange={(event) => {
              cancelRenameRef.current = false
              setDeckNameDraft({ deckId, value: event.target.value })
            }}
            onBlur={saveName}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                cancelRenameRef.current = false
                event.currentTarget.blur()
              }
              if (event.key === 'Escape') {
                cancelRenameRef.current = true
                setDeckNameDraft({ deckId, value: deckQuery.data.name })
                setRenameError(null)
                event.currentTarget.blur()
              }
            }}
            className="min-w-0 max-w-md flex-1 rounded border border-transparent bg-transparent px-2 py-1 text-sm font-semibold outline-none hover:border-slate-700 focus:border-blue-500 disabled:opacity-60"
          />
          <span aria-live="polite" className={saveState.kind === 'error' ? 'shrink-0 text-xs text-red-300' : 'shrink-0 text-xs text-slate-400'}>{statusText}</span>
          {renameError && <span role="alert" className="truncate text-xs text-red-300">{renameError}</span>}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm" variant="outline" disabled={navigationBlocked} className="border-slate-600 bg-slate-800 text-slate-100 hover:bg-slate-700" onClick={() => setVersionsOpen(true)}>Versions</Button>
          {navigationBlocked ? (
            <Button size="sm" disabled>Download</Button>
          ) : (
            <a href={deckDownloadUrl(deckId)} className="inline-flex h-8 items-center justify-center rounded-lg bg-citi-blue px-3 text-xs font-medium text-white hover:bg-[#045a92]">Download</a>
          )}
        </div>
      </header>

      <main className="h-[calc(100vh-48px)]">
        {isRestoring ? (
          <div className="grid h-full place-items-center bg-slate-950 p-6 text-center text-sm text-slate-300">
            {restoreSyncError ? (
              <div className="max-w-md">
                <p className="text-base font-semibold text-amber-200">Restored version is synchronizing</p>
                <p className="mt-2 text-sm text-slate-400">{restoreSyncError.message}</p>
                <Button className="mt-4" disabled={isSyncRetrying} onClick={retryRestoreSynchronization}>
                  {isSyncRetrying ? 'Retrying…' : 'Retry synchronization'}
                </Button>
              </div>
            ) : 'Restoring version…'}
          </div>
        ) : (
          <OnlyOfficeEditor
            key={`${currentStatus.current_version_id}:${editorAttempt}`}
            documentServerUrl={configQuery.data.document_server_url}
            config={configQuery.data.config}
            onDirtyChange={handleDirtyChange}
            onError={handleEditorError}
          />
        )}
      </main>

      <VersionHistoryDialog
        deckId={deckId}
        currentVersionId={currentStatus.current_version_id}
        open={versionsOpen}
        interactionsDisabled={navigationBlocked}
        onClose={() => setVersionsOpen(false)}
        onRestoringChange={(restoring) => {
          if (restoring) setRestoreSyncError(null)
          setIsRestoring(restoring)
        }}
        onRestored={(status) => {
          setRestoreSyncError(null)
          setSaveState({ kind: 'confirmed', version: status.current_version_number })
        }}
        onRestoreSyncError={(message, expected) => {
          setRestoreSyncError({ message, expected })
          setVersionsOpen(false)
        }}
      />
      {discardDialog}
    </div>
  )
}

function DiscardChangesDialog({
  open,
  onCancel,
  onDiscard,
}: {
  open: boolean
  onCancel: () => void
  onDiscard: () => void
}) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  return (
    <AccessibleModal open={open} labelledBy="discard-title" initialFocusRef={cancelRef} onRequestClose={onCancel} overlayClassName="z-[60] bg-black/70">
      <div className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900 p-5 text-slate-100 shadow-2xl">
        <h2 id="discard-title" className="text-lg font-semibold">Discard unsaved changes?</h2>
        <p className="mt-2 text-sm text-slate-400">The latest edits have not been confirmed in storage.</p>
        <div className="mt-5 flex justify-end gap-2">
          <button ref={cancelRef} type="button" onClick={onCancel} className="h-10 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-900 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-400/60">Keep editing</button>
          <Button onClick={onDiscard}>Discard and leave</Button>
        </div>
      </div>
    </AccessibleModal>
  )
}

function FailureView({
  message,
  onBack,
  onRetry,
}: {
  message: string
  onBack: () => void
  onRetry?: () => void
}) {
  return (
    <div className="grid h-screen place-items-center bg-slate-950 p-6 text-slate-100">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold">Unable to open deck</h1>
        <p className="mt-2 text-sm text-slate-400">{message}</p>
        <div className="mt-5 flex justify-center gap-3">
          <Button variant="outline" onClick={onBack}>Back</Button>
          {onRetry && <Button onClick={onRetry}>Retry</Button>}
        </div>
      </div>
    </div>
  )
}
