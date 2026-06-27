import { useEffect, useState } from 'react'
import { DeckContext, initialState, loadInitialState, STORAGE_KEY } from './deck'
import type { DeckContextValue } from './deck'
import type { DeckState } from '@/types'

export function DeckProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<DeckState>(loadInitialState)

  useEffect(() => {
    if (state.sessionId) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } else {
      sessionStorage.removeItem(STORAGE_KEY)
    }
  }, [state])

  const value: DeckContextValue = {
    state,
    setGeneratedDeck: (deck) => {
      setState({
        sessionId: deck.sessionId,
        savedDeckId: deck.savedDeckId ?? null,
        deckType: deck.deckType,
        slides: deck.slides,
        uploadedFile: deck.uploadedFile,
        lastExport: null,
      })
    },
    markDeckSaved: (deckId) => {
      setState((current) => ({ ...current, savedDeckId: deckId }))
    },
    updateSlide: (slide) => {
      setState((current) => ({
        ...current,
        slides: current.slides.map((existing) => (existing.index === slide.index ? slide : existing)),
        lastExport: null,
      }))
    },
    setExportResult: (result) => {
      setState((current) => ({ ...current, lastExport: result }))
    },
    clearDeck: () => setState(initialState),
  }

  return <DeckContext.Provider value={value}>{children}</DeckContext.Provider>
}
