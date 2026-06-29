import { render, screen } from '@testing-library/react'
import { Outlet } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('@/components/layout/Layout', () => ({
  Layout: () => <div data-testid="standard-layout"><Outlet /></div>,
}))
vi.mock('@/pages/LoginPage', () => ({ LoginPage: () => <div>Login page</div> }))
vi.mock('@/pages/CreatePage', () => ({ CreatePage: () => <div>Create page</div> }))
vi.mock('@/pages/PreviewPage', () => ({ PreviewPage: () => <div>Preview page</div> }))
vi.mock('@/pages/ExportPage', () => ({ ExportPage: () => <div>Export page</div> }))
vi.mock('@/pages/MyDecksPage', () => ({ MyDecksPage: () => <div>My decks page</div> }))
vi.mock('@/pages/EditorPage', () => ({ EditorPage: () => <div>Native editor page</div> }))
vi.mock('@/state/DeckContext', () => ({ DeckProvider: ({ children }: { children: React.ReactNode }) => children }))

describe('App routes', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/')
  })

  it('renders the native editor outside the standard application layout', () => {
    window.history.replaceState({}, '', '/editor/deck-1')
    render(<App />)

    expect(screen.getByText('Native editor page')).toBeInTheDocument()
    expect(screen.queryByTestId('standard-layout')).not.toBeInTheDocument()
  })

  it('keeps normal application pages inside the standard layout', () => {
    window.history.replaceState({}, '', '/create')
    render(<App />)

    expect(screen.getByText('Create page')).toBeInTheDocument()
    expect(screen.getByTestId('standard-layout')).toBeInTheDocument()
  })
})
