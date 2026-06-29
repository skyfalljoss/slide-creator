import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
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
  return (
    <QueryClientProvider client={queryClient}>
      <DeckProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/editor/:deckId" element={<EditorPage />} />
            <Route element={<Layout />}>
              <Route path="/create" element={<CreatePage />} />
              <Route path="/preview" element={<PreviewPage />} />
              <Route path="/export" element={<ExportPage />} />
              <Route path="/my-decks" element={<MyDecksPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/create" replace />} />
          </Routes>
        </BrowserRouter>
      </DeckProvider>
    </QueryClientProvider>
  )
}
