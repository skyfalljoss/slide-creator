import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DeckProvider } from '@/state/DeckContext'
import { DeckContext, initialState } from '@/state/deck'
import type { DeckContextValue } from '@/state/deck'
import { CreatePage } from './CreatePage'
import { generate, saveDeck, uploadFile } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  generate: vi.fn(),
  saveDeck: vi.fn(),
  uploadFile: vi.fn(),
}))

const navigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

function renderCreatePage(deckValue?: DeckContextValue) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const page = (
    <MemoryRouter>
      <CreatePage />
    </MemoryRouter>
  )
  return render(
    <QueryClientProvider client={queryClient}>
      {deckValue ? <DeckContext.Provider value={deckValue}>{page}</DeckContext.Provider> : <DeckProvider>{page}</DeckProvider>}
    </QueryClientProvider>,
  )
}

function deckContext(setGeneratedDeck = vi.fn()): DeckContextValue {
  return {
    state: initialState,
    setGeneratedDeck,
    markDeckSaved: vi.fn(),
    updateSlide: vi.fn(),
    setExportResult: vi.fn(),
    clearDeck: vi.fn(),
  }
}

describe('CreatePage', () => {
  beforeEach(() => {
    vi.mocked(generate).mockReset()
    vi.mocked(saveDeck).mockReset()
    vi.mocked(uploadFile).mockReset()
    navigate.mockReset()
    sessionStorage.clear()
  })

  it('keeps generate disabled until a prompt is entered', () => {
    renderCreatePage()

    expect(screen.getByRole('button', { name: /generate deck/i })).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/describe your presentation/i), { target: { value: 'Pitch for Acme' } })

    expect(screen.getByRole('button', { name: /generate deck/i })).toBeEnabled()
  })

  it('uploads a file then opens the generated persisted deck after generation resolves', async () => {
    let resolveGeneration: ((value: Awaited<ReturnType<typeof generate>>) => void) | undefined
    const generation = new Promise<Awaited<ReturnType<typeof generate>>>((resolve) => {
      resolveGeneration = resolve
    })
    vi.mocked(uploadFile).mockResolvedValue({ file_id: 'file-1.csv', filename: 'data.csv', row_count: 2, columns: ['quarter'], preview: 'quarter\nQ1' })
    vi.mocked(generate).mockReturnValue(generation)
    const result = {
      session_id: 'session-1',
      deck_id: 'deck-1',
      editor_path: '/editor/deck-1',
      slides: [{ index: 1, title: 'Title', bullets: [], notes: '', layout: 'title', chart_data: null }],
    } satisfies Awaited<ReturnType<typeof generate>>
    renderCreatePage()

    fireEvent.change(screen.getByLabelText(/describe your presentation/i), { target: { value: 'Pitch for Acme' } })
    fireEvent.change(screen.getByLabelText(/data file/i), { target: { files: [new File(['a,b'], 'data.csv', { type: 'text/csv' })] } })
    fireEvent.click(screen.getByRole('button', { name: /generate deck/i }))

    await waitFor(() => expect(generate).toHaveBeenCalledOnce())
    expect(navigate).not.toHaveBeenCalled()

    resolveGeneration?.(result)

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/editor/deck-1'))
    expect(vi.mocked(generate).mock.calls[0]?.[0]).toEqual({ prompt: 'Pitch for Acme', deck_type: 'sales_9', source_type: 'brief', target_audience: 'corporate', theme: 'minimalist', aspect_ratio: '16:9', file_id: 'file-1.csv' })
    expect(generate).toHaveBeenCalledOnce()
    expect(saveDeck).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(JSON.parse(sessionStorage.getItem('slideforge.deck') ?? '{}')).toMatchObject({
        sessionId: 'session-1',
        savedDeckId: 'deck-1',
        deckType: 'sales_9',
        slides: result.slides,
        uploadedFile: { file_id: 'file-1.csv' },
      })
    })
  })

  it('treats upload and generation as one critical section during rapid activation', async () => {
    let resolveUpload: ((value: Awaited<ReturnType<typeof uploadFile>>) => void) | undefined
    const upload = new Promise<Awaited<ReturnType<typeof uploadFile>>>((resolve) => {
      resolveUpload = resolve
    })
    let resolveGeneration: ((value: Awaited<ReturnType<typeof generate>>) => void) | undefined
    const generation = new Promise<Awaited<ReturnType<typeof generate>>>((resolve) => {
      resolveGeneration = resolve
    })
    const setGeneratedDeck = vi.fn()
    vi.mocked(uploadFile).mockReturnValue(upload)
    vi.mocked(generate).mockReturnValue(generation)
    renderCreatePage(deckContext(setGeneratedDeck))

    fireEvent.change(screen.getByLabelText(/describe your presentation/i), { target: { value: 'Pitch for Acme' } })
    fireEvent.change(screen.getByLabelText(/data file/i), { target: { files: [new File(['a,b'], 'data.csv', { type: 'text/csv' })] } })
    const button = screen.getByRole('button', { name: /generate deck/i })
    act(() => {
      button.click()
      button.click()
    })

    await waitFor(() => expect(uploadFile).toHaveBeenCalled())
    expect(uploadFile).toHaveBeenCalledOnce()
    resolveUpload?.({ file_id: 'file-1.csv', filename: 'data.csv', row_count: 2, columns: ['quarter'], preview: 'quarter\nQ1' })
    await waitFor(() => expect(generate).toHaveBeenCalledOnce())

    const result = {
      session_id: 'session-1',
      deck_id: 'deck-1',
      editor_path: '/editor/deck-1',
      slides: [{ index: 1, title: 'Title', bullets: [], notes: '', layout: 'title', chart_data: null }],
    } satisfies Awaited<ReturnType<typeof generate>>
    resolveGeneration?.(result)

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/editor/deck-1'))
    expect(uploadFile).toHaveBeenCalledOnce()
    expect(generate).toHaveBeenCalledOnce()
    expect(setGeneratedDeck).toHaveBeenCalledOnce()
    expect(setGeneratedDeck).toHaveBeenCalledWith({
      sessionId: 'session-1',
      savedDeckId: 'deck-1',
      deckType: 'sales_9',
      slides: result.slides,
      uploadedFile: { file_id: 'file-1.csv', filename: 'data.csv', row_count: 2, columns: ['quarter'], preview: 'quarter\nQ1' },
    })
    expect(navigate).toHaveBeenCalledOnce()
    expect(saveDeck).not.toHaveBeenCalled()
  })

  it('sends script source_type and selected audience', async () => {
    vi.mocked(generate).mockResolvedValue({
      session_id: 'session-2',
      deck_id: 'deck-2',
      editor_path: '/editor/deck-2',
      slides: [{ index: 1, title: 'Title', bullets: [], notes: '', layout: 'title', chart_data: null }],
    })
    renderCreatePage()

    fireEvent.click(screen.getByRole('button', { name: /paste script/i }))
    fireEvent.change(screen.getByLabelText(/paste your script/i), { target: { value: 'Para one.\n\nPara two.' } })
    fireEvent.change(screen.getByLabelText(/target audience/i), { target: { value: 'academic' } })
    fireEvent.click(screen.getByRole('button', { name: /dark mode/i }))
    fireEvent.click(screen.getByRole('button', { name: /4:3 standard/i }))
    fireEvent.click(screen.getByRole('button', { name: /generate deck/i }))

    await waitFor(() => expect(generate).toHaveBeenCalled())
    expect(vi.mocked(generate).mock.calls[0]?.[0]).toEqual({
      prompt: 'Para one.\n\nPara two.',
      deck_type: 'sales_9',
      source_type: 'script',
      target_audience: 'academic',
      theme: 'dark',
      aspect_ratio: '4:3',
      file_id: null,
    })
  })

  it('has no persistence or navigation side effects after rejection and permits one retry', async () => {
    const result = {
      session_id: 'session-2',
      deck_id: 'deck-2',
      editor_path: '/editor/deck-2',
      slides: [{ index: 1, title: 'Safe title', bullets: [], notes: '', layout: 'title', chart_data: null }],
    } satisfies Awaited<ReturnType<typeof generate>>
    vi.mocked(generate)
      .mockRejectedValueOnce(new Error('Prompt contains prohibited terms: risk-free'))
      .mockResolvedValueOnce(result)
    const setGeneratedDeck = vi.fn()
    renderCreatePage(deckContext(setGeneratedDeck))

    fireEvent.change(screen.getByLabelText(/describe your presentation/i), { target: { value: 'risk-free pitch' } })
    fireEvent.click(screen.getByRole('button', { name: /generate deck/i }))

    expect(await screen.findByText(/risk-free/i)).toBeInTheDocument()
    expect(navigate).not.toHaveBeenCalled()
    expect(setGeneratedDeck).not.toHaveBeenCalled()
    expect(saveDeck).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('slideforge.deck')).toBeNull()

    const retryButton = screen.getByRole('button', { name: /generate deck/i })
    await waitFor(() => expect(retryButton).toBeEnabled())
    fireEvent.click(retryButton)

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/editor/deck-2'))
    expect(generate).toHaveBeenCalledTimes(2)
    expect(setGeneratedDeck).toHaveBeenCalledOnce()
    expect(setGeneratedDeck).toHaveBeenCalledWith({
      sessionId: 'session-2',
      savedDeckId: 'deck-2',
      deckType: 'sales_9',
      slides: result.slides,
      uploadedFile: null,
    })
    expect(navigate).toHaveBeenCalledOnce()
    expect(saveDeck).not.toHaveBeenCalled()
  })
})
