import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DeckProvider } from '@/state/DeckContext'
import { PreviewPage } from './PreviewPage'
import { refine, saveDeck, updateDeck } from '@/lib/api'
import type { DeckState } from '@/types'

vi.mock('@/lib/api', () => ({ refine: vi.fn(), saveDeck: vi.fn(), updateDeck: vi.fn() }))

const storedDeck = {
  sessionId: 'session-1',
  deckType: 'sales_9',
  uploadedFile: null,
  lastExport: null,
  savedDeckId: 'deck-1',
  slides: [
    {
      index: 1,
      title: 'Executive Summary',
      bullets: ['First bullet'],
      notes: 'Speaker note',
      layout: 'content',
      chart_data: null,
      visual_direction: 'Use a right-side trend visual with Citi blue accents.',
      chart_recommendation: null,
      chart_audit: null,
    },
    {
      index: 2,
      title: 'Analysis',
      bullets: ['Second bullet'],
      notes: 'Another note',
      layout: 'chart',
      chart_data: { type: 'bar', title: 'Revenue', categories: ['Q1'], series: [{ name: 'revenue', values: [100] }] },
      visual_direction: 'Use a right-side bar chart with source notes.',
      chart_recommendation: null,
      chart_audit: {
        source_filename: 'revenue.csv',
        category_column: 'Quarter',
        value_columns: ['Revenue'],
        row_count: 1,
        chart_type: 'bar',
        recommendation_status: 'accepted',
        rejection_reason: null,
      },
    },
  ],
} satisfies DeckState

function renderPreview(initialPath = '/preview') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <DeckProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/preview" element={<PreviewPage />} />
            <Route path="/create" element={<div>Create route</div>} />
          </Routes>
        </MemoryRouter>
      </DeckProvider>
    </QueryClientProvider>,
  )
}

function renderPreviewWithDeckRoute(initialPath = '/preview') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

  const view = render(
    <QueryClientProvider client={queryClient}>
      <DeckProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/preview" element={<PreviewPage />} />
            <Route path="/my-decks" element={<div>My Decks route</div>} />
            <Route path="/create" element={<div>Create route</div>} />
          </Routes>
        </MemoryRouter>
      </DeckProvider>
    </QueryClientProvider>,
  )

  return { ...view, invalidateSpy }
}

describe('PreviewPage', () => {
  beforeEach(() => {
    vi.mocked(refine).mockReset()
    vi.mocked(saveDeck).mockReset()
    vi.mocked(updateDeck).mockReset()
    sessionStorage.clear()
  })

  it('redirects to create when no deck exists', () => {
    renderPreview()

    expect(screen.getByText('Create route')).toBeInTheDocument()
  })

  it('renders generated slides and chart indicators', () => {
    sessionStorage.setItem('slideforge.deck', JSON.stringify(storedDeck))

    renderPreview()

    expect(screen.getAllByText(/Executive Summary/i).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByText('Analysis'))
    expect(screen.getByText(/Chart: Revenue/i)).toBeInTheDocument()
    expect(screen.getByText(/Source: revenue.csv/i)).toBeInTheDocument()
    expect(screen.getByText(/Quarter, Revenue/i)).toBeInTheDocument()
  })

  it('shows design direction only after expanding the panel', () => {
    sessionStorage.setItem('slideforge.deck', JSON.stringify(storedDeck))

    renderPreview()

    expect(screen.queryByText(/right-side trend visual/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /design direction/i }))
    expect(screen.getByText(/right-side trend visual/i)).toBeInTheDocument()
  })

  it('refines the selected slide and updates state', async () => {
    sessionStorage.setItem('slideforge.deck', JSON.stringify(storedDeck))
    vi.mocked(refine).mockResolvedValue({ slide: { ...storedDeck.slides[0], title: 'Refined Summary', bullets: ['Updated bullet'] } })

    renderPreview()
    fireEvent.click(screen.getByRole('button', { name: /shorter/i }))

    await waitFor(() => expect(refine).toHaveBeenCalled())
    expect(vi.mocked(refine).mock.calls[0]?.[0]).toEqual({ session_id: 'session-1', slide_index: 1, instruction: 'Shorter' })
    await waitFor(() => expect(screen.getAllByText(/Refined Summary/i).length).toBeGreaterThan(0))
  })

  it('invalidates deck listings before navigating to my decks after save', async () => {
    sessionStorage.setItem('slideforge.deck', JSON.stringify(storedDeck))
    vi.mocked(updateDeck).mockResolvedValue({ updated_at: '2026-06-26T00:00:00Z' })

    const { invalidateSpy } = renderPreviewWithDeckRoute()
    fireEvent.click(screen.getByRole('button', { name: /update in my decks/i }))

    await waitFor(() => expect(updateDeck).toHaveBeenCalledWith('deck-1', { name: 'Executive Summary', slides: storedDeck.slides }))
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['decks'] }))
    await waitFor(() => expect(screen.getByText('My Decks route')).toBeInTheDocument())
  })
})
