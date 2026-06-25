import type { GenerateRequest, GenerateResponse, RefineRequest, RefineResponse, ExportRequest, ExportResponse, UploadResponse } from '@/types'

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
