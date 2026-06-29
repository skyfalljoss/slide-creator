import { StrictMode } from 'react'
import { act, render, screen } from '@testing-library/react'
import { createMemoryRouter, Outlet } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { createAppRoutes } from './appRouter'

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
  function renderApp(path: string) {
    const router = createMemoryRouter(createAppRoutes(), { initialEntries: [path] })
    return { router, ...render(<App router={router} />) }
  }

  it('renders the native editor outside the standard application layout', () => {
    renderApp('/editor/deck-1')

    expect(screen.getByText('Native editor page')).toBeInTheDocument()
    expect(screen.queryByTestId('standard-layout')).not.toBeInTheDocument()
  })

  it('keeps normal application pages inside the standard layout', () => {
    renderApp('/create')

    expect(screen.getByText('Create page')).toBeInTheDocument()
    expect(screen.getByTestId('standard-layout')).toBeInTheDocument()
  })

  it('keeps the router usable through StrictMode effect replay and POP navigation', async () => {
    const router = createMemoryRouter(createAppRoutes(), {
      initialEntries: ['/editor/deck-1', '/create'],
      initialIndex: 1,
    })
    const dispose = vi.spyOn(router, 'dispose')
    const { unmount } = render(
      <StrictMode>
        <App router={router} />
      </StrictMode>,
    )

    expect(screen.getByText('Create page')).toBeInTheDocument()
    expect(dispose).not.toHaveBeenCalled()
    await act(async () => router.navigate(-1))
    expect(screen.getByText('Native editor page')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/editor/deck-1')
    expect(dispose).not.toHaveBeenCalled()

    unmount()
    expect(dispose).not.toHaveBeenCalled()
  })
})
