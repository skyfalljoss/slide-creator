import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { deckDownloadUrl, deleteDeck, exportDeckById, listDecks } from '@/lib/api'
import { MyDecksPage } from './MyDecksPage'

vi.mock('@/lib/api', () => ({
  deckDownloadUrl: vi.fn((deckId: string) => `http://localhost:8000/api/v1/decks/${deckId}/download`),
  deleteDeck: vi.fn(),
  exportDeckById: vi.fn(),
  listDecks: vi.fn(),
}))

const navigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

function renderMyDecks() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <MyDecksPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MyDecksPage', () => {
  const open = vi.fn()

  beforeEach(() => {
    vi.mocked(deckDownloadUrl).mockClear()
    vi.mocked(deleteDeck).mockReset()
    vi.mocked(exportDeckById).mockReset()
    vi.mocked(listDecks).mockReset()
    navigate.mockReset()
    open.mockReset()
    vi.stubGlobal('open', open)
    vi.mocked(listDecks).mockResolvedValue({
      decks: [{
        id: 'deck-1',
        name: 'Persisted Deck',
        deck_type: 'sales_9',
        slide_count: 3,
        thumbnail_b64: null,
        created_at: '2026-06-26T00:00:00Z',
        updated_at: '2026-06-26T00:00:00Z',
      }],
    })
  })

  it('downloads the persisted PPTX in the same browser context', async () => {
    renderMyDecks()

    fireEvent.click(await screen.findByRole('button', { name: /download/i }))

    expect(deckDownloadUrl).toHaveBeenCalledWith('deck-1')
    expect(open).toHaveBeenCalledWith('http://localhost:8000/api/v1/decks/deck-1/download', '_self')
    expect(exportDeckById).not.toHaveBeenCalled()
  })

  it('preserves direct edit and delete behavior', async () => {
    vi.mocked(deleteDeck).mockResolvedValue({ ok: true })
    renderMyDecks()

    fireEvent.click(await screen.findByRole('button', { name: /edit/i }))
    expect(navigate).toHaveBeenCalledWith('/editor/deck-1')

    fireEvent.click(screen.getByRole('button', { name: /delete/i }))
    fireEvent.click(within(screen.getByRole('heading', { name: /delete this deck/i }).parentElement!).getByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(vi.mocked(deleteDeck).mock.calls[0]?.[0]).toBe('deck-1'))
  })
})
