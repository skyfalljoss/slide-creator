import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { exportDeck, generate, refine, uploadFile } from './api'

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
})
