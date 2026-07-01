import { useEffect, useId, useRef } from 'react'
import { loadOnlyOfficeApi } from '@/lib/onlyoffice'

interface OnlyOfficeEditorProps {
  documentServerUrl: string
  config: Record<string, unknown>
  onDirtyChange: (dirty: boolean) => void
  onError: (message: string) => void
}

type OnlyOfficeEvent = { data?: unknown; [key: string]: unknown }
type OnlyOfficeEventHandler = (event: OnlyOfficeEvent) => void

function eventHandler(value: unknown): OnlyOfficeEventHandler | undefined {
  return typeof value === 'function' ? value as OnlyOfficeEventHandler : undefined
}

function errorMessage(event: OnlyOfficeEvent): string {
  if (typeof event.data === 'string' && event.data.trim()) return event.data
  if (event.data && typeof event.data === 'object') {
    const description = (event.data as { errorDescription?: unknown }).errorDescription
    if (typeof description === 'string' && description.trim()) return description
  }
  return 'ONLYOFFICE reported an editor error'
}

export function OnlyOfficeEditor({
  documentServerUrl,
  config,
  onDirtyChange,
  onError,
}: OnlyOfficeEditorProps) {
  const reactId = useId()
  const containerId = `onlyoffice-editor-${reactId.replace(/[^a-zA-Z0-9_-]/g, '')}`
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const placeholder = document.createElement('div')
    placeholder.id = containerId
    placeholder.className = 'h-full w-full'
    host.replaceChildren(placeholder)
    let disposed = false
    let destroyed = false
    let editor: { destroyEditor(): void } | undefined
    const sourceEvents = config.events && typeof config.events === 'object'
      ? config.events as Record<string, unknown>
      : {}
    const backendStateChange = eventHandler(sourceEvents.onDocumentStateChange)
    const backendError = eventHandler(sourceEvents.onError)
    const mergedConfig = {
      ...config,
      events: {
        ...sourceEvents,
        onDocumentStateChange: (event: OnlyOfficeEvent) => {
          try {
            backendStateChange?.(event)
          } finally {
            onDirtyChange(event.data === true)
          }
        },
        onError: (event: OnlyOfficeEvent) => {
          try {
            backendError?.(event)
          } finally {
            onError(errorMessage(event))
          }
        },
      },
    }

    const destroy = () => {
      if (!editor || destroyed) return
      destroyed = true
      editor.destroyEditor()
    }

    void loadOnlyOfficeApi(documentServerUrl)
      .then((docsApi) => {
        if (disposed) return
        try {
          editor = new docsApi.DocEditor(containerId, mergedConfig)
        } catch (error) {
          if (!disposed) {
            onError(error instanceof Error ? error.message : 'Failed to start ONLYOFFICE editor')
          }
        }
      })
      .catch((error: unknown) => {
        if (!disposed) {
          onError(error instanceof Error ? error.message : 'Failed to load ONLYOFFICE editor')
        }
      })

    return () => {
      disposed = true
      destroy()
      host.replaceChildren()
    }
  }, [config, containerId, documentServerUrl, onDirtyChange, onError])

  return <div ref={hostRef} className="h-full w-full" data-testid="onlyoffice-editor" />
}
