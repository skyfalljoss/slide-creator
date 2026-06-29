import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { deckDownloadUrl, deleteDeck, listDecks } from '@/lib/api'
import type { DeckSummary } from '@/types'

const DECK_TYPE_LABELS: Record<string, string> = {
  sales_9: 'Sales Pitch',
  internal_6: 'Internal Update',
}

const DECK_TYPE_COLORS: Record<string, string> = {
  sales_9: 'from-citi-blue to-blue-900',
  internal_6: 'from-citi-red to-red-900',
}

const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'name', label: 'Name A-Z' },
]

export function MyDecksPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [deckTypeFilter, setDeckTypeFilter] = useState('')
  const [sort, setSort] = useState('newest')
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['decks', search, deckTypeFilter, sort],
    queryFn: () => listDecks({ q: search, deck_type: deckTypeFilter, sort }),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteDeck,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['decks'] })
      setDeleteConfirm(null)
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to delete'),
  })

  const decks = data?.decks ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-white">My Decks</h2>
          <p className="mt-1 text-slate-400">{decks.length} saved decks</p>
        </div>
        <Button variant="glow" onClick={() => navigate('/create')}>+ New Deck</Button>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search decks..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[200px] rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-citi-blue"
        />
        <select
          value={deckTypeFilter}
          onChange={(e) => setDeckTypeFilter(e.target.value)}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        >
          <option value="">All Types</option>
          <option value="sales_9">Sales Pitch (9)</option>
          <option value="internal_6">Internal Update (6)</option>
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">Dismiss</button>
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse rounded-xl border border-white/10 bg-white/5 h-48" />
          ))}
        </div>
      ) : decks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="text-5xl mb-4">📭</div>
          <h3 className="text-xl font-semibold text-white">No decks yet</h3>
          <p className="mt-2 text-slate-400">Generate your first pitch deck to get started.</p>
          <Button variant="glow" className="mt-6" onClick={() => navigate('/create')}>
            Create your first deck
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {decks.map((deck: DeckSummary) => (
            <div key={deck.id} className="overflow-hidden rounded-xl border border-white/10 bg-white/5 transition hover:border-white/20">
              <div className={cn('h-28 flex items-center justify-center bg-gradient-to-br', DECK_TYPE_COLORS[deck.deck_type] || 'from-slate-700 to-slate-900')}>
                <div className="text-center">
                  <div className="text-2xl mb-1">{deck.deck_type === 'sales_9' ? '📊' : '📋'}</div>
                  <div className="text-xs text-white/70">{deck.slide_count} Slides</div>
                </div>
              </div>
              <div className="p-4">
                <div className="font-semibold text-white truncate">{deck.name}</div>
                <div className="text-xs text-slate-400 mt-0.5">
                  {DECK_TYPE_LABELS[deck.deck_type] || deck.deck_type} · {new Date(deck.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </div>
                <div className="flex gap-2 mt-3">
                  <Button size="sm" onClick={() => navigate(`/editor/${deck.id}`)}>Edit</Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-white/15 bg-white/5 text-slate-200 hover:border-indigo-400/50 hover:bg-white/10"
                    onClick={() => window.open(deckDownloadUrl(deck.id), '_self')}
                  >
                    Download
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                    onClick={() => setDeleteConfirm(deck.id)}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-card p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-semibold text-white">Delete this deck?</h3>
            <p className="mt-2 text-sm text-slate-400">This action cannot be undone.</p>
            <div className="flex gap-3 mt-4 justify-end">
              <Button variant="outline" className="border-white/15 bg-white/5 text-slate-200" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
              <Button
                variant="glow"
                className="bg-citi-red hover:bg-red-600"
                onClick={() => deleteMutation.mutate(deleteConfirm)}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
