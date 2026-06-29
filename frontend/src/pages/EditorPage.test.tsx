import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EditorPage } from './EditorPage'
import {
  getDeck,
  getDeckStatus,
  getEditorConfig,
  listDeckVersions,
  renameDeck,
  restoreDeckVersion,
} from '@/lib/api'
import { loadOnlyOfficeApi } from '@/lib/onlyoffice'
import type { OnlyOfficeDocsApi } from '@/lib/onlyoffice'
import type { DeckDetail, DeckStatus } from '@/types'

vi.mock('@/lib/api', () => ({
  deckDownloadUrl: vi.fn((deckId: string) => `/api/v1/decks/${deckId}/download`),
  getDeck: vi.fn(),
  getDeckStatus: vi.fn(),
  getEditorConfig: vi.fn(),
  listDeckVersions: vi.fn(),
  renameDeck: vi.fn(),
  restoreDeckVersion: vi.fn(),
}))

vi.mock('@/lib/onlyoffice', () => ({ loadOnlyOfficeApi: vi.fn() }))

const deck: DeckDetail = {
  id: 'deck-1',
  name: 'Quarterly Review',
  deck_type: 'internal_6',
  theme: 'minimalist',
  aspect_ratio: '16:9',
  slides: [],
  thumbnail_b64: null,
  created_at: '2026-06-26T00:00:00Z',
  updated_at: '2026-06-26T00:00:00Z',
}

const versionOne: DeckStatus = {
  current_version_id: 'version-1',
  current_version_number: 1,
  updated_at: '2026-06-26T00:00:00Z',
}

function configFor(versionId: string, marker?: string) {
  return {
    document_server_url: 'http://onlyoffice.test',
    config: {
      ...(marker ? { marker } : {}),
      document: { key: `deck-1-${versionId}`, title: deck.name },
      editorConfig: { mode: 'edit' },
    },
  }
}

let editorConfigs: Record<string, unknown>[]
let editorElementIds: string[]
let destroyEditor: ReturnType<typeof vi.fn>

function renderEditor(initialEntries = ['/my-decks', '/editor/deck-1'], initialIndex = initialEntries.length - 1) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter([
    { path: '/editor/:deckId', element: <EditorPage /> },
    { path: '/my-decks', element: <div>Deck library</div> },
  ], { initialEntries, initialIndex })
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...result, queryClient, router }
}

function documentStateHandler() {
  return editorConfigs[editorConfigs.length - 1].events as {
    onDocumentStateChange: (event: { data: boolean }) => void
  }
}

describe('EditorPage', () => {
  beforeEach(() => {
    editorConfigs = []
    editorElementIds = []
    destroyEditor = vi.fn()
    vi.mocked(getDeck).mockReset().mockResolvedValue(deck)
    vi.mocked(getEditorConfig).mockReset().mockResolvedValue(configFor('version-1'))
    vi.mocked(getDeckStatus).mockReset().mockResolvedValue(versionOne)
    vi.mocked(listDeckVersions).mockReset().mockResolvedValue({ versions: [] })
    vi.mocked(renameDeck).mockReset().mockResolvedValue({ ...deck, name: 'Renamed deck' })
    vi.mocked(restoreDeckVersion).mockReset()
    vi.mocked(loadOnlyOfficeApi).mockReset().mockResolvedValue({
      DocEditor: class {
        constructor(elementId: string, config: Record<string, unknown>) {
          editorElementIds.push(elementId)
          editorConfigs.push(config)
        }

        destroyEditor = destroyEditor
      },
    } as unknown as OnlyOfficeDocsApi)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('hosts ONLYOFFICE with the backend configuration and destroys it on unmount', async () => {
    const { unmount } = renderEditor()

    expect(await screen.findByDisplayValue('Quarterly Review')).toBeInTheDocument()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))
    expect(editorConfigs[0]).toMatchObject({
      document: { title: 'Quarterly Review' },
      editorConfig: { mode: 'edit' },
    })
    expect(editorElementIds[0]).toMatch(/^onlyoffice-editor-/)

    unmount()
    expect(destroyEditor).toHaveBeenCalledTimes(1)
  })

  it('moves from unsaved to pending and confirms the next persisted version', async () => {
    vi.mocked(getDeckStatus)
      .mockResolvedValueOnce(versionOne)
      .mockResolvedValueOnce(versionOne)
      .mockResolvedValue({
        current_version_id: 'version-2',
        current_version_number: 2,
        updated_at: '2026-06-26T00:01:00Z',
      })
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    expect(screen.getByText('Unsaved')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download' })).toBeDisabled()

    act(() => documentStateHandler().onDocumentStateChange({ data: false }))
    expect(screen.getByText('Saving…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download' })).toBeDisabled()

    await waitFor(() => expect(screen.getByText('Saved as version 2')).toBeInTheDocument(), {
      timeout: 4_000,
    })
    expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute(
      'href',
      '/api/v1/decks/deck-1/download',
    )
  })

  it('warns before unloading only while dirty or awaiting persistence', async () => {
    vi.mocked(getDeckStatus).mockResolvedValueOnce(versionOne).mockResolvedValue({
      current_version_id: 'version-2',
      current_version_number: 2,
      updated_at: '2026-06-26T00:01:00Z',
    })
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    const cleanEvent = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(cleanEvent)
    expect(cleanEvent.defaultPrevented).toBe(false)

    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    const dirtyEvent = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirtyEvent)
    expect(dirtyEvent.defaultPrevented).toBe(true)

    act(() => documentStateHandler().onDocumentStateChange({ data: false }))
    const pendingEvent = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(pendingEvent)
    expect(pendingEvent.defaultPrevented).toBe(true)

    await screen.findByText('Saved as version 2', {}, { timeout: 3_000 })
    const savedEvent = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(savedEvent)
    expect(savedEvent.defaultPrevented).toBe(false)
  })

  it('stops save polling after the 30 second hard limit', async () => {
    vi.mocked(getDeckStatus).mockResolvedValue(versionOne)
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))
    vi.useFakeTimers()
    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    act(() => documentStateHandler().onDocumentStateChange({ data: false }))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000)
    })

    expect(screen.getByText('Save confirmation timed out')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Versions' })).toBeDisabled()
    const unsafeEvent = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unsafeEvent)
    expect(unsafeEvent.defaultPrevented).toBe(true)
    const callsAtTimeout = vi.mocked(getDeckStatus).mock.calls.length
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
    })
    expect(getDeckStatus).toHaveBeenCalledTimes(callsAtTimeout)
  })

  it('keeps a failed save unsafe and guards navigation', async () => {
    vi.mocked(getDeckStatus)
      .mockResolvedValueOnce(versionOne)
      .mockRejectedValueOnce(new Error('Persistence confirmation failed'))
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))
    vi.useFakeTimers()
    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    act(() => documentStateHandler().onDocumentStateChange({ data: false }))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000)
    })

    expect(screen.getByText('Persistence confirmation failed')).toBeInTheDocument()
    const unsafeEvent = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unsafeEvent)
    expect(unsafeEvent.defaultPrevented).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByRole('dialog', { name: 'Discard unsaved changes?' })).toBeInTheDocument()
  })

  it('captures the dirty baseline before status advances and confirms immediately on clean', async () => {
    const { queryClient } = renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    act(() => {
      queryClient.setQueryData(['deck-status', 'deck-1'], {
        current_version_id: 'version-2',
        current_version_number: 2,
        updated_at: '2026-06-26T00:01:00Z',
      })
    })
    act(() => documentStateHandler().onDocumentStateChange({ data: false }))

    expect(screen.getByText('Saved as version 2')).toBeInTheDocument()
    expect(getDeckStatus).toHaveBeenCalledTimes(1)
  })

  it('tracks repeated dirty and clean save cycles', async () => {
    vi.mocked(getDeckStatus)
      .mockResolvedValueOnce(versionOne)
      .mockResolvedValueOnce({ ...versionOne, current_version_id: 'version-2', current_version_number: 2 })
      .mockResolvedValue({ ...versionOne, current_version_id: 'version-3', current_version_number: 3 })
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    act(() => documentStateHandler().onDocumentStateChange({ data: false }))
    expect(await screen.findByText('Saved as version 2', {}, { timeout: 2_000 })).toBeInTheDocument()

    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    act(() => documentStateHandler().onDocumentStateChange({ data: false }))
    expect(await screen.findByText('Saved as version 3', {}, { timeout: 2_000 })).toBeInTheDocument()
  })

  it('does not let an earlier save confirm edits made during a pending save', async () => {
    vi.mocked(getDeckStatus)
      .mockResolvedValueOnce(versionOne)
      .mockResolvedValueOnce({ ...versionOne, current_version_id: 'version-2', current_version_number: 2 })
      .mockResolvedValue({ ...versionOne, current_version_id: 'version-3', current_version_number: 3 })
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))
    vi.useFakeTimers()

    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    act(() => documentStateHandler().onDocumentStateChange({ data: false }))
    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    act(() => documentStateHandler().onDocumentStateChange({ data: false }))

    await act(async () => vi.advanceTimersByTimeAsync(1_000))
    expect(screen.getByText('Saving…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download' })).toBeDisabled()

    await act(async () => vi.advanceTimersByTimeAsync(1_000))
    expect(screen.getByText('Saved as version 3')).toBeInTheDocument()
  })

  it('requires deliberate discard before Back navigation while unsafe', async () => {
    const { router } = renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))
    act(() => documentStateHandler().onDocumentStateChange({ data: true }))

    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    const dialog = screen.getByRole('dialog', { name: 'Discard unsaved changes?' })
    expect(screen.queryByText('Deck library')).not.toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/editor/deck-1')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep editing' }))
    expect(screen.queryByRole('dialog', { name: 'Discard unsaved changes?' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Discard and leave' }))
    expect(await screen.findByText('Deck library')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/my-decks')
  })

  it('makes discard confirmation keyboard-modal and restores focus on Escape', async () => {
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))
    const back = screen.getByRole('button', { name: /Back/ })
    back.focus()
    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    fireEvent.click(back)

    const dialog = screen.getByRole('dialog', { name: 'Discard unsaved changes?' })
    const keep = within(dialog).getByRole('button', { name: 'Keep editing' })
    const discard = within(dialog).getByRole('button', { name: 'Discard and leave' })
    expect(keep).toHaveFocus()
    expect(screen.getByRole('main', { hidden: true })).toHaveAttribute('inert')
    fireEvent.keyDown(keep, { key: 'Tab', shiftKey: true })
    expect(discard).toHaveFocus()
    fireEvent.keyDown(discard, { key: 'Tab' })
    expect(keep).toHaveFocus()

    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Discard unsaved changes?' })).not.toBeInTheDocument()
    expect(back).toHaveFocus()
  })

  it('intercepts browser history navigation while unsafe', async () => {
    const { router } = renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))
    act(() => documentStateHandler().onDocumentStateChange({ data: true }))

    await act(async () => router.navigate(-1))
    const dialog = screen.getByRole('dialog', { name: 'Discard unsaved changes?' })
    expect(screen.queryByText('Deck library')).not.toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/editor/deck-1')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep editing' }))

    await act(async () => router.navigate(-1))
    const repeatedDialog = screen.getByRole('dialog', { name: 'Discard unsaved changes?' })
    expect(router.state.location.pathname).toBe('/editor/deck-1')
    fireEvent.click(within(repeatedDialog).getByRole('button', { name: 'Discard and leave' }))

    expect(await screen.findByText('Deck library')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/my-decks')
  })

  it('navigates Back cleanly from a direct editor entry', async () => {
    const { router } = renderEditor(['/editor/deck-1'])
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    fireEvent.click(screen.getByRole('button', { name: /Back/ }))

    expect(await screen.findByText('Deck library')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/my-decks')
    expect(screen.queryByRole('dialog', { name: 'Discard unsaved changes?' })).not.toBeInTheDocument()
  })

  it('removes navigation blocking when the editor unmounts', async () => {
    const { router, unmount } = renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))
    act(() => documentStateHandler().onDocumentStateChange({ data: true }))
    unmount()

    await router.navigate('/my-decks')

    expect(router.state.location.pathname).toBe('/my-decks')
    expect(router.state.blockers.size).toBe(0)
  })

  it('shows retry and back actions when editor configuration fails', async () => {
    vi.mocked(getEditorConfig)
      .mockRejectedValueOnce(new Error('Configuration unavailable'))
      .mockResolvedValueOnce({
        document_server_url: 'http://onlyoffice.test',
        config: { document: { title: deck.name } },
      })
    renderEditor()

    expect(await screen.findByText('Configuration unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    expect(await screen.findByText('Deck library')).toBeInTheDocument()
  })

  it.each([
    ['deck', getDeck],
    ['status', getDeckStatus],
  ] as const)('shows a recoverable failure when the %s request fails', async (_name, request) => {
    vi.mocked(request).mockRejectedValueOnce(new Error('Request unavailable'))
    renderEditor()

    expect(await screen.findByText('Request unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
  })

  it('renames the deck on blur and exposes a recoverable rename error', async () => {
    vi.mocked(renameDeck)
      .mockRejectedValueOnce(new Error('Name rejected'))
      .mockResolvedValueOnce({ ...deck, name: 'Accepted name' })
    renderEditor()
    const nameInput = await screen.findByDisplayValue('Quarterly Review')

    fireEvent.change(nameInput, { target: { value: 'Rejected name' } })
    fireEvent.blur(nameInput)
    expect(await screen.findByText('Name rejected')).toBeInTheDocument()

    fireEvent.change(nameInput, { target: { value: 'Accepted name' } })
    fireEvent.blur(nameInput)
    await waitFor(() => expect(renameDeck).toHaveBeenLastCalledWith('deck-1', 'Accepted name'))
    await waitFor(() => expect(screen.queryByText('Name rejected')).not.toBeInTheDocument())
  })

  it('cancels rename on Escape without sending a PATCH', async () => {
    renderEditor()
    const nameInput = await screen.findByRole('textbox', { name: 'Deck name' })

    nameInput.focus()
    fireEvent.change(nameInput, { target: { value: 'Do not save this' } })
    fireEvent.keyDown(nameInput, { key: 'Escape' })

    expect(nameInput).toHaveValue('Quarterly Review')
    expect(renameDeck).not.toHaveBeenCalled()
  })

  it('commits rename once when Enter causes blur', async () => {
    renderEditor()
    const nameInput = await screen.findByRole('textbox', { name: 'Deck name' })
    nameInput.focus()
    fireEvent.change(nameInput, { target: { value: 'One rename' } })
    fireEvent.keyDown(nameInput, { key: 'Enter' })
    fireEvent.blur(nameInput)

    await waitFor(() => expect(renameDeck).toHaveBeenCalledWith('deck-1', 'One rename'))
    expect(renameDeck).toHaveBeenCalledTimes(1)
  })

  it('lists versions newest first and requires confirmation before restore', async () => {
    vi.mocked(getEditorConfig)
      .mockResolvedValueOnce(configFor('version-3'))
      .mockResolvedValue(configFor('version-4'))
    vi.mocked(listDeckVersions).mockResolvedValue({
      versions: [
        { id: 'version-1', version_number: 1, source: 'generated', created_by: 'user', created_at: '2026-06-26T00:00:00Z', size_bytes: 10, sha256: 'one' },
        { id: 'version-3', version_number: 3, source: 'onlyoffice_save', created_by: 'user', created_at: '2026-06-26T00:02:00Z', size_bytes: 30, sha256: 'three' },
        { id: 'version-2', version_number: 2, source: 'onlyoffice_save', created_by: 'user', created_at: '2026-06-26T00:01:00Z', size_bytes: 20, sha256: 'two' },
      ],
    })
    vi.mocked(restoreDeckVersion).mockResolvedValue({
      current_version_id: 'version-4',
      current_version_number: 4,
      updated_at: '2026-06-26T00:03:00Z',
    })
    vi.mocked(getDeckStatus)
      .mockResolvedValueOnce({ ...versionOne, current_version_id: 'version-3', current_version_number: 3 })
      .mockResolvedValue({
        current_version_id: 'version-4',
        current_version_number: 4,
        updated_at: '2026-06-26T00:03:00Z',
      })
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    fireEvent.click(screen.getByRole('button', { name: 'Versions' }))
    const dialog = await screen.findByRole('dialog', { name: 'Version history' })
    const rows = await within(dialog).findAllByTestId('version-row')
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining('Version 3'),
      expect.stringContaining('Version 2'),
      expect.stringContaining('Version 1'),
    ])

    fireEvent.click(within(rows[2]).getByRole('button', { name: 'Restore version 1' }))
    expect(restoreDeckVersion).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm restore version 1' }))

    await waitFor(() => expect(restoreDeckVersion).toHaveBeenCalledWith('deck-1', 'version-1'))
    await waitFor(() => expect(editorConfigs).toHaveLength(2))
    expect(destroyEditor).toHaveBeenCalledTimes(1)
  })

  it('does not mount a restored editor until fresh status and config both arrive', async () => {
    let resolveConfig!: (value: { document_server_url: string; config: Record<string, unknown> }) => void
    const delayedConfig = new Promise<{ document_server_url: string; config: Record<string, unknown> }>((resolve) => {
      resolveConfig = resolve
    })
    vi.mocked(getEditorConfig)
      .mockResolvedValueOnce(configFor('version-2', 'old'))
      .mockReturnValueOnce(delayedConfig)
    vi.mocked(listDeckVersions).mockResolvedValue({
      versions: [
        { id: 'version-1', version_number: 1, source: 'generated', created_by: 'user', created_at: '2026-06-26T00:00:00Z', size_bytes: 10, sha256: 'one' },
      ],
    })
    vi.mocked(getDeckStatus)
      .mockResolvedValueOnce({ ...versionOne, current_version_id: 'version-2', current_version_number: 2 })
      .mockResolvedValue({ ...versionOne, current_version_id: 'version-3', current_version_number: 3 })
    vi.mocked(restoreDeckVersion).mockResolvedValue({
      current_version_id: 'version-3',
      current_version_number: 3,
      updated_at: '2026-06-26T00:02:00Z',
    })
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    fireEvent.click(screen.getByRole('button', { name: 'Versions' }))
    const dialog = await screen.findByRole('dialog', { name: 'Version history' })
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Restore version 1' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm restore version 1' }))

    expect(await screen.findByText('Restoring version…')).toBeInTheDocument()
    expect(destroyEditor).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(getEditorConfig).toHaveBeenCalledTimes(2))
    expect(editorConfigs).toHaveLength(1)

    await act(async () => {
      resolveConfig(configFor('version-3', 'fresh'))
    })
    await waitFor(() => expect(editorConfigs).toHaveLength(2))
    expect(editorConfigs[1]).toMatchObject({ marker: 'fresh' })
  })

  it('keeps the editor gated while restored status is stale and recovers without restoring twice', async () => {
    vi.mocked(listDeckVersions).mockResolvedValue({
      versions: [{ id: 'version-1', version_number: 1, source: 'generated', created_by: 'user', created_at: '2026-06-26T00:00:00Z', size_bytes: 10, sha256: 'one' }],
    })
    vi.mocked(restoreDeckVersion).mockResolvedValue({
      current_version_id: 'version-3', current_version_number: 3, updated_at: '2026-06-26T00:02:00Z',
    })
    vi.mocked(getDeckStatus)
      .mockResolvedValueOnce({ ...versionOne, current_version_id: 'version-2', current_version_number: 2 })
      .mockResolvedValueOnce({ ...versionOne, current_version_id: 'version-2', current_version_number: 2 })
      .mockResolvedValue({ ...versionOne, current_version_id: 'version-3', current_version_number: 3 })
    vi.mocked(getEditorConfig)
      .mockResolvedValueOnce(configFor('version-2'))
      .mockResolvedValue(configFor('version-3'))
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    fireEvent.click(screen.getByRole('button', { name: 'Versions' }))
    const dialog = await screen.findByRole('dialog', { name: 'Version history' })
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Restore version 1' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm restore version 1' }))

    expect(await screen.findByText(/restored status is not current/i)).toBeInTheDocument()
    expect(editorConfigs).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Retry synchronization' }))
    await waitFor(() => expect(editorConfigs).toHaveLength(2))
    expect(restoreDeckVersion).toHaveBeenCalledTimes(1)
  })

  it('keeps the editor gated while restored config is stale and recovers without restoring twice', async () => {
    vi.mocked(listDeckVersions).mockResolvedValue({
      versions: [{ id: 'version-1', version_number: 1, source: 'generated', created_by: 'user', created_at: '2026-06-26T00:00:00Z', size_bytes: 10, sha256: 'one' }],
    })
    vi.mocked(restoreDeckVersion).mockResolvedValue({
      current_version_id: 'version-3', current_version_number: 3, updated_at: '2026-06-26T00:02:00Z',
    })
    vi.mocked(getDeckStatus)
      .mockResolvedValueOnce({ ...versionOne, current_version_id: 'version-2', current_version_number: 2 })
      .mockResolvedValue({ ...versionOne, current_version_id: 'version-3', current_version_number: 3 })
    vi.mocked(getEditorConfig)
      .mockResolvedValueOnce(configFor('version-2'))
      .mockResolvedValueOnce(configFor('version-2'))
      .mockResolvedValue(configFor('version-3'))
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    fireEvent.click(screen.getByRole('button', { name: 'Versions' }))
    const dialog = await screen.findByRole('dialog', { name: 'Version history' })
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Restore version 1' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm restore version 1' }))

    expect(await screen.findByText(/editor config is not current/i)).toBeInTheDocument()
    expect(editorConfigs).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Retry synchronization' }))
    await waitFor(() => expect(editorConfigs).toHaveLength(2))
    expect(restoreDeckVersion).toHaveBeenCalledTimes(1)
  })

  it('keeps the editor gated after a restore refetch failure and retries synchronization only', async () => {
    vi.mocked(listDeckVersions).mockResolvedValue({
      versions: [{ id: 'version-1', version_number: 1, source: 'generated', created_by: 'user', created_at: '2026-06-26T00:00:00Z', size_bytes: 10, sha256: 'one' }],
    })
    vi.mocked(restoreDeckVersion).mockResolvedValue({
      current_version_id: 'version-3', current_version_number: 3, updated_at: '2026-06-26T00:02:00Z',
    })
    vi.mocked(getDeckStatus)
      .mockResolvedValueOnce({ ...versionOne, current_version_id: 'version-2', current_version_number: 2 })
      .mockResolvedValue({ ...versionOne, current_version_id: 'version-3', current_version_number: 3 })
    vi.mocked(getEditorConfig)
      .mockResolvedValueOnce(configFor('version-2'))
      .mockRejectedValueOnce(new Error('Config replica unavailable'))
      .mockResolvedValue(configFor('version-3'))
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))

    fireEvent.click(screen.getByRole('button', { name: 'Versions' }))
    const dialog = await screen.findByRole('dialog', { name: 'Version history' })
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Restore version 1' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm restore version 1' }))

    expect(await screen.findByText(/Config replica unavailable/i)).toBeInTheDocument()
    expect(editorConfigs).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Retry synchronization' }))
    await waitFor(() => expect(editorConfigs).toHaveLength(2))
    expect(restoreDeckVersion).toHaveBeenCalledTimes(1)
  })

  it('traps focus in version history and restores it to the opener', async () => {
    vi.mocked(getDeckStatus).mockResolvedValue({ ...versionOne, current_version_id: 'version-2', current_version_number: 2 })
    vi.mocked(listDeckVersions).mockResolvedValue({
      versions: [
        { id: 'version-1', version_number: 1, source: 'generated', created_by: 'user', created_at: '2026-06-26T00:00:00Z', size_bytes: 10, sha256: 'one' },
      ],
    })
    renderEditor()
    const opener = await screen.findByRole('button', { name: 'Versions' })
    opener.focus()
    fireEvent.click(opener)
    const dialog = await screen.findByRole('dialog', { name: 'Version history' })
    const close = within(dialog).getByRole('button', { name: 'Close version history' })
    await waitFor(() => expect(close).toHaveFocus())
    expect(screen.getByRole('main', { hidden: true })).toHaveAttribute('aria-hidden', 'true')

    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true })
    const restore = await within(dialog).findByRole('button', { name: 'Restore version 1' })
    expect(restore).toHaveFocus()
    fireEvent.keyDown(restore, { key: 'Tab' })
    expect(close).toHaveFocus()

    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Version history' })).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })

  it('disables restore actions if the document becomes unsafe while history is open', async () => {
    vi.mocked(getDeckStatus).mockResolvedValue({ ...versionOne, current_version_id: 'version-2', current_version_number: 2 })
    vi.mocked(listDeckVersions).mockResolvedValue({
      versions: [
        { id: 'version-1', version_number: 1, source: 'generated', created_by: 'user', created_at: '2026-06-26T00:00:00Z', size_bytes: 10, sha256: 'one' },
      ],
    })
    renderEditor()
    await waitFor(() => expect(editorConfigs).toHaveLength(1))
    fireEvent.click(screen.getByRole('button', { name: 'Versions' }))
    const dialog = await screen.findByRole('dialog', { name: 'Version history' })
    const restore = await within(dialog).findByRole('button', { name: 'Restore version 1' })
    expect(restore).toBeEnabled()

    act(() => documentStateHandler().onDocumentStateChange({ data: true }))

    expect(restore).toBeDisabled()
  })

  it('keeps the version dialog open and reports restore failures', async () => {
    vi.mocked(listDeckVersions).mockResolvedValue({
      versions: [
        { id: 'version-1', version_number: 1, source: 'generated', created_by: 'user', created_at: '2026-06-26T00:00:00Z', size_bytes: 10, sha256: 'one' },
      ],
    })
    vi.mocked(restoreDeckVersion).mockRejectedValue(new Error('Restore failed'))
    vi.mocked(getDeckStatus).mockResolvedValue({
      current_version_id: 'version-2',
      current_version_number: 2,
      updated_at: '2026-06-26T00:01:00Z',
    })
    renderEditor()
    fireEvent.click(await screen.findByRole('button', { name: 'Versions' }))
    const dialog = await screen.findByRole('dialog', { name: 'Version history' })
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Restore version 1' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm restore version 1' }))

    expect(await within(dialog).findByText('Restore failed')).toBeInTheDocument()
    expect(dialog).toBeInTheDocument()
  })
})
