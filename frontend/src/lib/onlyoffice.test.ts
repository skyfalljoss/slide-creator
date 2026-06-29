import { afterEach, describe, expect, it, vi } from 'vitest'

describe('loadOnlyOfficeApi', () => {
  afterEach(() => {
    document.head.replaceChildren()
    delete window.DocsAPI
    vi.resetModules()
  })

  it('normalizes the base URL and shares one script between concurrent callers', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')

    const first = loadOnlyOfficeApi('https://office.example.test///')
    const second = loadOnlyOfficeApi('https://office.example.test')
    const scripts = document.querySelectorAll('script')

    expect(scripts).toHaveLength(1)
    expect(scripts[0]?.src).toBe('https://office.example.test/web-apps/apps/api/documents/api.js')

    const DocEditor = vi.fn(function () {
      return { destroyEditor: vi.fn() }
    })
    window.DocsAPI = { DocEditor }
    scripts[0]?.dispatchEvent(new Event('load'))

    await expect(first).resolves.toBe(window.DocsAPI)
    await expect(second).resolves.toBe(window.DocsAPI)
  })

  it('waits for an existing matching script instead of appending another', async () => {
    const script = document.createElement('script')
    script.src = 'https://office.example.test/web-apps/apps/api/documents/api.js'
    document.head.append(script)
    const { loadOnlyOfficeApi } = await import('./onlyoffice')

    const loading = loadOnlyOfficeApi('https://office.example.test/')

    expect(document.querySelectorAll('script')).toHaveLength(1)
    window.DocsAPI = { DocEditor: vi.fn() }
    script.dispatchEvent(new Event('load'))
    await expect(loading).resolves.toBe(window.DocsAPI)
  })

  it('rejects script errors and permits a clean retry', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')

    const failed = loadOnlyOfficeApi('https://office.example.test')
    const firstScript = document.querySelector('script')
    firstScript?.dispatchEvent(new Event('error'))

    await expect(failed).rejects.toThrow('Failed to load ONLYOFFICE Docs API')
    expect(document.querySelectorAll('script')).toHaveLength(0)

    const retried = loadOnlyOfficeApi('https://office.example.test')
    const retryScript = document.querySelector('script')
    window.DocsAPI = { DocEditor: vi.fn() }
    retryScript?.dispatchEvent(new Event('load'))

    await expect(retried).resolves.toBe(window.DocsAPI)
  })

  it('rejects when the loaded script does not expose DocEditor', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')

    const loading = loadOnlyOfficeApi('https://office.example.test')
    document.querySelector('script')?.dispatchEvent(new Event('load'))

    await expect(loading).rejects.toThrow('did not expose DocsAPI.DocEditor')
  })
})
