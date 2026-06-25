import { createContext, useContext } from 'react'
import type { DeckState, DeckType, ExportResponse, SlideData, UploadResponse } from '@/types'

export const STORAGE_KEY = 'slideforge.deck'

export const initialState: DeckState = {
  sessionId: null,
  deckType: null,
  slides: [],
  uploadedFile: null,
  lastExport: null,
}

export interface SetGeneratedDeckInput {
  sessionId: string
  deckType: DeckType
  slides: SlideData[]
  uploadedFile: UploadResponse | null
}

export interface DeckContextValue {
  state: DeckState
  setGeneratedDeck: (deck: SetGeneratedDeckInput) => void
  updateSlide: (slide: SlideData) => void
  setExportResult: (result: ExportResponse) => void
  clearDeck: () => void
}

export const DeckContext = createContext<DeckContextValue | null>(null)

export function loadInitialState(): DeckState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? { ...initialState, ...JSON.parse(raw) } : initialState
  } catch {
    return initialState
  }
}

export function useDeck() {
  const context = useContext(DeckContext)
  if (!context) {
    throw new Error('useDeck must be used within DeckProvider')
  }
  return context
}
