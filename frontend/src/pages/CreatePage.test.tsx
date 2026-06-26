import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DeckProvider } from '@/state/DeckContext'
import { CreatePage } from './CreatePage'
import { generate, uploadFile } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  generate: vi.fn(),
  uploadFile: vi.fn(),
}))

const navigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

function renderCreatePage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <DeckProvider>
        <MemoryRouter>
          <CreatePage />
        </MemoryRouter>
      </DeckProvider>
    </QueryClientProvider>,
  )
}

describe('CreatePage', () => {
  beforeEach(() => {
    vi.mocked(generate).mockReset()
    vi.mocked(uploadFile).mockReset()
    navigate.mockReset()
    sessionStorage.clear()
  })

  it('keeps generate disabled until a prompt is entered', () => {
    renderCreatePage()

    expect(screen.getByRole('button', { name: /generate deck/i })).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/describe your presentation/i), { target: { value: 'Pitch for Acme' } })

    expect(screen.getByRole('button', { name: /generate deck/i })).toBeEnabled()
  })

  it('uploads a file then generates with the returned file_id', async () => {
    vi.mocked(uploadFile).mockResolvedValue({ file_id: 'file-1.csv', filename: 'data.csv', row_count: 2, columns: ['quarter'], preview: 'quarter\nQ1' })
    vi.mocked(generate).mockResolvedValue({
      session_id: 'session-1',
      slides: [{ index: 1, title: 'Title', bullets: [], notes: '', layout: 'title', chart_data: null }],
    })
    renderCreatePage()

    fireEvent.change(screen.getByLabelText(/describe your presentation/i), { target: { value: 'Pitch for Acme' } })
    fireEvent.change(screen.getByLabelText(/data file/i), { target: { files: [new File(['a,b'], 'data.csv', { type: 'text/csv' })] } })
    fireEvent.click(screen.getByRole('button', { name: /generate deck/i }))

    await waitFor(() => expect(uploadFile).toHaveBeenCalled())
    expect(vi.mocked(generate).mock.calls[0]?.[0]).toEqual({ prompt: 'Pitch for Acme', deck_type: 'sales_9', source_type: 'brief', target_audience: 'corporate', theme: 'minimalist', aspect_ratio: '16:9', file_id: 'file-1.csv' })
    expect(navigate).toHaveBeenCalledWith('/preview')
  })

  it('sends script source_type and selected audience', async () => {
    vi.mocked(generate).mockResolvedValue({
      session_id: 'session-2',
      slides: [{ index: 1, title: 'Title', bullets: [], notes: '', layout: 'title', chart_data: null }],
    })
    renderCreatePage()

    fireEvent.click(screen.getByRole('button', { name: /paste script/i }))
    fireEvent.change(screen.getByLabelText(/paste your script/i), { target: { value: 'Para one.\n\nPara two.' } })
    fireEvent.change(screen.getByLabelText(/target audience/i), { target: { value: 'academic' } })
    fireEvent.click(screen.getByRole('button', { name: /dark mode/i }))
    fireEvent.click(screen.getByRole('button', { name: /4:3 standard/i }))
    fireEvent.click(screen.getByRole('button', { name: /generate deck/i }))

    await waitFor(() => expect(generate).toHaveBeenCalled())
    expect(vi.mocked(generate).mock.calls[0]?.[0]).toEqual({
      prompt: 'Para one.\n\nPara two.',
      deck_type: 'sales_9',
      source_type: 'script',
      target_audience: 'academic',
      theme: 'dark',
      aspect_ratio: '4:3',
      file_id: null,
    })
  })

  it('renders backend errors', async () => {
    vi.mocked(generate).mockRejectedValue(new Error('Prompt contains prohibited terms: risk-free'))
    renderCreatePage()

    fireEvent.change(screen.getByLabelText(/describe your presentation/i), { target: { value: 'risk-free pitch' } })
    fireEvent.click(screen.getByRole('button', { name: /generate deck/i }))

    expect(await screen.findByText(/risk-free/i)).toBeInTheDocument()
  })
})
