import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { OnlyOfficeEditor } from './OnlyOfficeEditor'
import { loadOnlyOfficeApi } from '@/lib/onlyoffice'
import type { OnlyOfficeDocsApi } from '@/lib/onlyoffice'

vi.mock('@/lib/onlyoffice', () => ({ loadOnlyOfficeApi: vi.fn() }))

describe('OnlyOfficeEditor', () => {
  beforeEach(() => {
    vi.mocked(loadOnlyOfficeApi).mockReset()
  })

  it('uses unique stable container IDs and preserves backend event handlers without mutation', async () => {
    const backendStateHandler = vi.fn()
    const onDirtyChange = vi.fn()
    const config = { events: { onDocumentStateChange: backendStateHandler }, marker: 'backend' }
    const received: Array<{ id: string; config: Record<string, unknown> }> = []
    vi.mocked(loadOnlyOfficeApi).mockResolvedValue({
      DocEditor: class {
        constructor(id: string, mergedConfig: Record<string, unknown>) {
          received.push({ id, config: mergedConfig })
        }
        destroyEditor = vi.fn()
      },
    } as unknown as OnlyOfficeDocsApi)

    const { rerender } = render(
      <>
        <OnlyOfficeEditor documentServerUrl="http://onlyoffice.test" config={config} onDirtyChange={onDirtyChange} onError={vi.fn()} />
        <OnlyOfficeEditor documentServerUrl="http://onlyoffice.test" config={{ marker: 'second' }} onDirtyChange={vi.fn()} onError={vi.fn()} />
      </>,
    )
    await waitFor(() => expect(received).toHaveLength(2))
    expect(received[0].id).not.toBe(received[1].id)
    const firstId = received[0].id
    expect(received[0].config).not.toBe(config)
    expect(received[0].config.events).not.toBe(config.events)
    expect(config.events.onDocumentStateChange).toBe(backendStateHandler)

    const mergedHandler = (received[0].config.events as {
      onDocumentStateChange: (event: { data: boolean }) => void
    }).onDocumentStateChange
    act(() => mergedHandler({ data: true }))
    expect(backendStateHandler).toHaveBeenCalledWith({ data: true })
    expect(onDirtyChange).toHaveBeenCalledWith(true)

    rerender(
      <OnlyOfficeEditor documentServerUrl="http://onlyoffice.test" config={config} onDirtyChange={onDirtyChange} onError={vi.fn()} />,
    )
    expect(document.getElementById(firstId)).toBeInTheDocument()
  })

  it('does not instantiate from a stale loader result after unmount', async () => {
    let resolveApi!: (api: OnlyOfficeDocsApi) => void
    const constructor = vi.fn()
    vi.mocked(loadOnlyOfficeApi).mockReturnValue(new Promise((resolve) => {
      resolveApi = resolve
    }))
    const { unmount } = render(
      <OnlyOfficeEditor documentServerUrl="http://onlyoffice.test" config={{}} onDirtyChange={vi.fn()} onError={vi.fn()} />,
    )
    unmount()

    await act(async () => {
      resolveApi({ DocEditor: constructor as unknown as OnlyOfficeDocsApi['DocEditor'] })
      await Promise.resolve()
    })
    expect(constructor).not.toHaveBeenCalled()
  })

  it('destroys each instantiated editor exactly once across remount and unmount', async () => {
    const destroyers: ReturnType<typeof vi.fn>[] = []
    vi.mocked(loadOnlyOfficeApi).mockResolvedValue({
      DocEditor: class {
        constructor() {
          destroyers.push(this.destroyEditor)
        }
        destroyEditor = vi.fn()
      },
    } as unknown as OnlyOfficeDocsApi)
    const { rerender, unmount } = render(
      <OnlyOfficeEditor key="version-1" documentServerUrl="http://onlyoffice.test" config={{ version: 1 }} onDirtyChange={vi.fn()} onError={vi.fn()} />,
    )
    await waitFor(() => expect(destroyers).toHaveLength(1))

    rerender(
      <OnlyOfficeEditor key="version-2" documentServerUrl="http://onlyoffice.test" config={{ version: 2 }} onDirtyChange={vi.fn()} onError={vi.fn()} />,
    )
    await waitFor(() => expect(destroyers).toHaveLength(2))
    expect(destroyers[0]).toHaveBeenCalledTimes(1)

    unmount()
    expect(destroyers[0]).toHaveBeenCalledTimes(1)
    expect(destroyers[1]).toHaveBeenCalledTimes(1)
  })

  it('keeps React DOM ownership stable when ONLYOFFICE replaces its placeholder', async () => {
    vi.mocked(loadOnlyOfficeApi).mockResolvedValue({
      DocEditor: class {
        private frame: HTMLIFrameElement

        constructor(id: string) {
          const placeholder = document.getElementById(id)
          if (!placeholder?.parentNode) throw new Error('Editor placeholder is missing')
          this.frame = document.createElement('iframe')
          this.frame.dataset.onlyofficeFrame = id
          placeholder.parentNode.replaceChild(this.frame, placeholder)
        }

        destroyEditor = () => {
          this.frame.remove()
        }
      },
    } as unknown as OnlyOfficeDocsApi)
    const props = {
      documentServerUrl: 'http://onlyoffice.test',
      onDirtyChange: vi.fn(),
      onError: vi.fn(),
    }
    const { rerender, unmount } = render(
      <OnlyOfficeEditor key="version-1" {...props} config={{ version: 1 }} />,
    )
    await waitFor(() => expect(document.querySelector('[data-onlyoffice-frame]')).toBeInTheDocument())

    expect(() => rerender(
      <OnlyOfficeEditor key="version-2" {...props} config={{ version: 2 }} />,
    )).not.toThrow()
    await waitFor(() => expect(document.querySelector('[data-onlyoffice-frame]')).toBeInTheDocument())
    expect(() => unmount()).not.toThrow()
  })

  it('reports loader failures and never attempts destruction without an instance', async () => {
    const onError = vi.fn()
    vi.mocked(loadOnlyOfficeApi).mockRejectedValue(new Error('Docs API unavailable'))
    const { unmount } = render(
      <OnlyOfficeEditor documentServerUrl="http://onlyoffice.test" config={{}} onDirtyChange={vi.fn()} onError={onError} />,
    )
    await waitFor(() => expect(onError).toHaveBeenCalledWith('Docs API unavailable'))
    expect(() => unmount()).not.toThrow()
  })
})
