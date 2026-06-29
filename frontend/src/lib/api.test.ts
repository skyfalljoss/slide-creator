import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  deckDownloadUrl,
  exportDeck,
  generate,
  getDeckSlidePreview,
  getDeckStatus,
  getEditorConfig,
  listDeckVersions,
  refine,
  renameDeck,
  restoreDeckVersion,
  uploadFile,
} from './api'

describe('api client', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uploads files using multipart form data', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ file_id: 'file-1.csv', filename: 'data.csv', row_count: 1, columns: ['quarter'], preview: 'quarter\nQ1' }),
    })
    const file = new File(['quarter\nQ1'], 'data.csv', { type: 'text/csv' })

    const result = await uploadFile(file)

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/v1/uploads', {
      method: 'POST',
      body: expect.any(FormData),
    })
    expect(result.file_id).toBe('file-1.csv')
  })

  it('sends JSON requests for generation, refinement, and export', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ session_id: 's1', slides: [] }) })

    await generate({ prompt: 'Pitch', deck_type: 'sales_9', file_id: 'file-1.csv' })

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/v1/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: 'Pitch', deck_type: 'sales_9', file_id: 'file-1.csv' }),
    })

    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ slide: { index: 1, title: 'Updated', bullets: [], notes: '', layout: 'content', chart_data: null } }) })
    await refine({ session_id: 's1', slide_index: 1, instruction: 'Shorter' })

    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ download_url: '/api/v1/download/s1.pptx', expires_at: '2026-06-17T12:00:00Z' }) })
    await exportDeck({ session_id: 's1' })
  })

  it('throws readable backend errors', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Prompt contains prohibited terms: risk-free' }),
    })

    await expect(generate({ prompt: 'risk-free pitch', deck_type: 'sales_9' })).rejects.toThrow('Prompt contains prohibited terms: risk-free')
  })

  it('fetches deck slide previews', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ deck_id: 'deck-1', slide_index: 2, image_b64: 'UE5H', width: 1920, height: 1080, updated_at: 'now' }),
    })

    const result = await getDeckSlidePreview('deck-1', 2)

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/v1/decks/deck-1/preview?slide_index=2')
    expect(result.image_b64).toBe('UE5H')
    expect(result.width).toBe(1920)
  })

  it('uses the persisted deck editor, status, and version routes', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) })

    await getEditorConfig('deck-1')
    await getDeckStatus('deck-1')
    await listDeckVersions('deck-1')
    await restoreDeckVersion('deck-1', 'version-2')

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://localhost:8000/api/v1/decks/deck-1/editor-config')
    expect(fetchMock).toHaveBeenNthCalledWith(2, 'http://localhost:8000/api/v1/decks/deck-1/status')
    expect(fetchMock).toHaveBeenNthCalledWith(3, 'http://localhost:8000/api/v1/decks/deck-1/versions')
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      'http://localhost:8000/api/v1/decks/deck-1/versions/version-2/restore',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      },
    )
  })

  it('renames decks with PATCH and exposes the direct download URL', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'deck-1', name: 'Renamed' }) })

    await renameDeck('deck-1', 'Renamed')

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/v1/decks/deck-1', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Renamed' }),
    })
    expect(deckDownloadUrl('deck-1')).toBe('http://localhost:8000/api/v1/decks/deck-1/download')
  })

  it('encodes deck and version IDs as individual URL path segments', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) })
    const deckId = 'deck/with space?'
    const versionId = 'version/#2'

    await getEditorConfig(deckId)
    await getDeckStatus(deckId)
    await listDeckVersions(deckId)
    await restoreDeckVersion(deckId, versionId)
    await renameDeck(deckId, 'Renamed')

    const encodedDeckId = 'deck%2Fwith%20space%3F'
    expect(fetchMock).toHaveBeenNthCalledWith(1, `http://localhost:8000/api/v1/decks/${encodedDeckId}/editor-config`)
    expect(fetchMock).toHaveBeenNthCalledWith(2, `http://localhost:8000/api/v1/decks/${encodedDeckId}/status`)
    expect(fetchMock).toHaveBeenNthCalledWith(3, `http://localhost:8000/api/v1/decks/${encodedDeckId}/versions`)
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      `http://localhost:8000/api/v1/decks/${encodedDeckId}/versions/version%2F%232/restore`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      `http://localhost:8000/api/v1/decks/${encodedDeckId}`,
      expect.objectContaining({ method: 'PATCH' }),
    )
    expect(deckDownloadUrl(deckId)).toBe(`http://localhost:8000/api/v1/decks/${encodedDeckId}/download`)
  })
})
