import { useEffect, useState } from 'react'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from '@/components/layout/Layout'
import { LoginPage } from '@/pages/LoginPage'
import { CreatePage } from '@/pages/CreatePage'
import { PreviewPage } from '@/pages/PreviewPage'
import { ExportPage } from '@/pages/ExportPage'
import { MyDecksPage } from '@/pages/MyDecksPage'
import { EditorPage } from '@/pages/EditorPage'
import { DeckProvider } from '@/state/DeckContext'

const queryClient = new QueryClient()

export default function App() {
  const [router] = useState(() => createBrowserRouter([
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
  ]))
  useEffect(() => () => router.dispose(), [router])
  return (
    <QueryClientProvider client={queryClient}>
      <DeckProvider>
        <RouterProvider router={router} />
      </DeckProvider>
    </QueryClientProvider>
  )
}
