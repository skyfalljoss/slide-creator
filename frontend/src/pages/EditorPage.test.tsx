import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EditorPage } from './EditorPage'
import { getDeck, getDeckSlidePreview, updateDeck, exportDeckById } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  getDeck: vi.fn(),
  getDeckSlidePreview: vi.fn(),
  updateDeck: vi.fn(),
  exportDeckById: vi.fn(),
}))

function renderEditor() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/editor/deck-1']}>
        <Routes>
          <Route path="/editor/:deckId" element={<EditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('EditorPage', () => {
  beforeEach(() => {
    vi.mocked(getDeck).mockReset()
    vi.mocked(getDeckSlidePreview).mockReset()
    vi.mocked(updateDeck).mockReset()
    vi.mocked(exportDeckById).mockReset()
    vi.mocked(getDeckSlidePreview).mockResolvedValue({
      deck_id: 'deck-1',
      slide_index: 1,
      image_b64: 'UE5H',
      width: 1920,
      height: 1080,
      updated_at: '2026-06-26T00:00:00Z',
    })
    vi.mocked(updateDeck).mockResolvedValue({ updated_at: '2026-06-26T00:01:00Z' })
    vi.mocked(exportDeckById).mockResolvedValue({ download_url: 'http://test/deck.pptx', expires_at: '2026-06-26T00:05:00Z' })
    vi.spyOn(window, 'open').mockImplementation(() => null)
    vi.mocked(getDeck).mockResolvedValue({
      id: 'deck-1',
      name: 'Editor Test Deck',
      deck_type: 'sales_9',
      theme: 'minimalist',
      aspect_ratio: '16:9',
      thumbnail_b64: null,
      created_at: '2026-06-26T00:00:00Z',
      updated_at: '2026-06-26T00:00:00Z',
      slides: [
        {
          index: 1,
          title: 'Editable Slide',
          bullets: ['First point'],
          notes: 'Speaker note',
          layout: 'title',
          chart_data: null,
        },
      ],
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the editor with the backend PPTX preview image', async () => {
    renderEditor()

    expect(await screen.findByDisplayValue('Editor Test Deck')).toBeInTheDocument()
    expect(screen.getByText('Slide 1 of 1')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Editable Slide')).toBeInTheDocument()
    expect(await screen.findByAltText('Slide 1 preview')).toHaveAttribute('src', 'data:image/png;base64,UE5H')
    expect(getDeckSlidePreview).toHaveBeenCalledWith('deck-1', 1)
  })

  it('flushes dirty slide changes before export', async () => {
    renderEditor()

    expect(await screen.findByDisplayValue('Editor Test Deck')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Updated Slide' } })
    fireEvent.click(screen.getByRole('button', { name: 'Export PPTX' }))

    await waitFor(() => expect(updateDeck).toHaveBeenCalledWith('deck-1', expect.objectContaining({
      slides: [expect.objectContaining({ title: 'Updated Slide' })],
    })))
    await waitFor(() => expect(exportDeckById).toHaveBeenCalledWith('deck-1'))
  })
})
