import { createBrowserRouter, createMemoryRouter, Navigate } from 'react-router-dom'
import type { RouteObject } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { LoginPage } from '@/pages/LoginPage'
import { CreatePage } from '@/pages/CreatePage'
import { PreviewPage } from '@/pages/PreviewPage'
import { ExportPage } from '@/pages/ExportPage'
import { MyDecksPage } from '@/pages/MyDecksPage'
import { EditorPage } from '@/pages/EditorPage'

export function createAppRoutes(): RouteObject[] {
  return [
    { path: '/login', element: <LoginPage /> },
    { path: '/editor/:deckId', element: <EditorPage /> },
    {
      element: <Layout />,
      children: [
        { path: '/create', element: <CreatePage /> },
        { path: '/preview', element: <PreviewPage /> },
        { path: '/export', element: <ExportPage /> },
        { path: '/my-decks', element: <MyDecksPage /> },
      ],
    },
    { path: '*', element: <Navigate to="/create" replace /> },
  ]
}

export type AppRouter = ReturnType<typeof createBrowserRouter>
let productionRouter: AppRouter | undefined

export function getProductionRouter(): AppRouter {
  if (!productionRouter) {
    productionRouter = typeof window === 'undefined'
      ? createMemoryRouter(createAppRoutes(), { initialEntries: ['/'] })
      : createBrowserRouter(createAppRoutes())
  }
  return productionRouter
}
