import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { getProductionRouter } from '@/appRouter'
import type { AppRouter } from '@/appRouter'
import { DeckProvider } from '@/state/DeckContext'

const queryClient = new QueryClient()

export default function App({ router }: { router?: AppRouter }) {
  const appRouter = router ?? getProductionRouter()
  return (
    <QueryClientProvider client={queryClient}>
      <DeckProvider>
        <RouterProvider router={appRouter} />
      </DeckProvider>
    </QueryClientProvider>
  )
}
