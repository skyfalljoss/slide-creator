import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import type { ExportResponse, SlideData, UploadResponse } from '@/types'
import { DeckProvider } from './DeckContext'
import { useDeck } from './deck'

const slide: SlideData = {
  index: 1,
  title: 'Executive Summary',
  bullets: ['First bullet'],
  notes: 'Speaker note',
  layout: 'content',
  chart_data: null,
}

const upload: UploadResponse = {
  file_id: 'file-1.csv',
  filename: 'data.csv',
  row_count: 1,
  columns: ['quarter'],
  preview: 'quarter\nQ1',
}

function Harness() {
  const deck = useDeck()
  return (
    <div>
      <div data-testid="session">{deck.state.sessionId ?? 'none'}</div>
      <div data-testid="slide-title">{deck.state.slides[0]?.title ?? 'none'}</div>
      <div data-testid="export">{deck.state.lastExport?.download_url ?? 'none'}</div>
      <button onClick={() => deck.setGeneratedDeck({ sessionId: 's1', deckType: 'sales_9', slides: [slide], uploadedFile: upload })}>set</button>
      <button onClick={() => deck.updateSlide({ ...slide, title: 'Updated' })}>update</button>
      <button onClick={() => deck.setExportResult({ download_url: '/download/s1.pptx', expires_at: '2026-06-17T12:00:00Z' })}>export</button>
      <button onClick={deck.clearDeck}>clear</button>
    </div>
  )
}

describe('DeckProvider', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('stores generated decks and updates slides', () => {
    render(<DeckProvider><Harness /></DeckProvider>)

    act(() => screen.getByText('set').click())
    expect(screen.getByTestId('session')).toHaveTextContent('s1')
    expect(screen.getByTestId('slide-title')).toHaveTextContent('Executive Summary')

    act(() => screen.getByText('update').click())
    expect(screen.getByTestId('slide-title')).toHaveTextContent('Updated')
  })

  it('stores export results and clears deck state', () => {
    render(<DeckProvider><Harness /></DeckProvider>)

    act(() => screen.getByText('set').click())
    act(() => screen.getByText('export').click())
    expect(screen.getByTestId('export')).toHaveTextContent('/download/s1.pptx')

    act(() => screen.getByText('clear').click())
    expect(screen.getByTestId('session')).toHaveTextContent('none')
    expect(screen.getByTestId('export')).toHaveTextContent('none')
  })

  it('clears existing export results when a slide changes', () => {
    render(<DeckProvider><Harness /></DeckProvider>)

    act(() => screen.getByText('set').click())
    act(() => screen.getByText('export').click())
    expect(screen.getByTestId('export')).toHaveTextContent('/download/s1.pptx')

    act(() => screen.getByText('update').click())
    expect(screen.getByTestId('export')).toHaveTextContent('none')
  })

  it('hydrates from sessionStorage', () => {
    const stored = {
      sessionId: 'stored-session',
      deckType: 'internal_6',
      slides: [{ ...slide, title: 'Stored Slide' }],
      uploadedFile: null,
      lastExport: null satisfies ExportResponse | null,
    }
    sessionStorage.setItem('slideforge.deck', JSON.stringify(stored))

    render(<DeckProvider><Harness /></DeckProvider>)

    expect(screen.getByTestId('session')).toHaveTextContent('stored-session')
    expect(screen.getByTestId('slide-title')).toHaveTextContent('Stored Slide')
  })
})
