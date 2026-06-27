import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DeckProvider } from '@/state/DeckContext'
import { ExportPage } from './ExportPage'
import { exportDeck } from '@/lib/api'
import type { DeckState } from '@/types'

vi.mock('@/lib/api', () => ({ exportDeck: vi.fn() }))

const storedDeck = {
  sessionId: 'session-1',
  savedDeckId: null,
  deckType: 'sales_9',
  uploadedFile: null,
  lastExport: null,
  slides: [{ index: 1, title: 'Title', bullets: [], notes: '', layout: 'title', chart_data: null }],
} satisfies DeckState

function renderExport() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <DeckProvider>
        <MemoryRouter initialEntries={['/export']}>
          <Routes>
            <Route path="/export" element={<ExportPage />} />
            <Route path="/preview" element={<div>Preview route</div>} />
          </Routes>
        </MemoryRouter>
      </DeckProvider>
    </QueryClientProvider>,
  )
}

describe('ExportPage', () => {
  beforeEach(() => {
    vi.mocked(exportDeck).mockReset()
    sessionStorage.clear()
  })

  it('redirects to preview when no deck exists', () => {
    renderExport()

    expect(screen.getByText('Preview route')).toBeInTheDocument()
  })

  it('exports the current session and renders a download link', async () => {
    sessionStorage.setItem('slideforge.deck', JSON.stringify(storedDeck))
    vi.mocked(exportDeck).mockResolvedValue({ download_url: '/api/v1/download/session-1.pptx', expires_at: '2099-06-17T12:00:00Z' })

    renderExport()
    fireEvent.click(screen.getByRole('button', { name: /export as pptx/i }))

    await waitFor(() => expect(exportDeck).toHaveBeenCalled())
    expect(vi.mocked(exportDeck).mock.calls[0]?.[0]).toEqual({ session_id: 'session-1' })
    expect(await screen.findByRole('link', { name: /download pptx/i })).toHaveAttribute('href', '/api/v1/download/session-1.pptx')
  })

  it('allows re-export when a persisted export link is expired', () => {
    sessionStorage.setItem('slideforge.deck', JSON.stringify({
      ...storedDeck,
      lastExport: { download_url: '/api/v1/download/old.pptx', expires_at: '2000-01-01T00:00:00Z' },
    }))

    renderExport()

    expect(screen.getByRole('button', { name: /export as pptx/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /download pptx/i })).not.toBeInTheDocument()
  })
})
