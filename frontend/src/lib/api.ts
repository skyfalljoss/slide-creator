import type {
  GenerateRequest, GenerateResponse,
  RefineRequest, RefineResponse,
  ExportRequest, ExportResponse,
  UploadResponse,
  ListDecksResponse, DeckDetail,
  SaveDeckRequest, SaveDeckResponse,
  UpdateDeckRequest, UpdateDeckResponse,
} from '@/types'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

async function request<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function parseError(res: Response): Promise<Error> {
  const err = await res.json().catch(() => ({ detail: res.statusText }))
  return new Error(err.detail || 'Request failed')
}

async function getRequest<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value) url.searchParams.set(key, value)
    }
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    throw await parseError(res)
  }
  return res.json()
}

export function generate(data: GenerateRequest): Promise<GenerateResponse> {
  return request('/generate', data)
}

export async function uploadFile(file: File): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE_URL}/uploads`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    throw await parseError(res)
  }
  return res.json()
}

export function refine(data: RefineRequest): Promise<RefineResponse> {
  return request('/refine', data)
}

export function exportDeck(data: ExportRequest): Promise<ExportResponse> {
  return request('/export', data)
}

export function listDecks(params?: { q?: string; deck_type?: string; sort?: string }): Promise<ListDecksResponse> {
  return getRequest('/decks', params)
}

export function getDeck(deckId: string): Promise<DeckDetail> {
  return getRequest(`/decks/${deckId}`)
}

export function saveDeck(data: SaveDeckRequest): Promise<SaveDeckResponse> {
  return request('/decks', data)
}

export function updateDeck(deckId: string, data: UpdateDeckRequest): Promise<UpdateDeckResponse> {
  return fetch(`${BASE_URL}/decks/${deckId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(async (res) => {
    if (!res.ok) throw await parseError(res)
    return res.json()
  })
}

export async function deleteDeck(deckId: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE_URL}/decks/${deckId}`, { method: 'DELETE' })
  if (!res.ok) throw await parseError(res)
  return res.json()
}

export function exportDeckById(deckId: string): Promise<ExportResponse> {
  return request('/export', { deck_id: deckId })
}
