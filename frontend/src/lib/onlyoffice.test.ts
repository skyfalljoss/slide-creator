import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('loadOnlyOfficeApi', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    document.head.replaceChildren()
    delete window.DocsAPI
    vi.resetModules()
  })

  it('canonicalizes equivalent proxy base URLs and shares their promise and script', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')

    const first = loadOnlyOfficeApi(' HTTPS://OFFICE.EXAMPLE.TEST:443/onlyoffice/// ')
    const second = loadOnlyOfficeApi('https://office.example.test/onlyoffice')
    const scripts = document.querySelectorAll('script')

    expect(first).toBe(second)
    expect(scripts).toHaveLength(1)
    expect(scripts[0]?.src).toBe('https://office.example.test/onlyoffice/web-apps/apps/api/documents/api.js')

    window.DocsAPI = { DocEditor: vi.fn() }
    scripts[0]?.dispatchEvent(new Event('load'))

    await expect(first).resolves.toBe(window.DocsAPI)
  })

  it('normalizes the root path without creating a double slash', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')
    const loading = loadOnlyOfficeApi('https://office.example.test///')

    expect(document.querySelector('script')?.src).toBe(
      'https://office.example.test/web-apps/apps/api/documents/api.js',
    )
    window.DocsAPI = { DocEditor: vi.fn() }
    document.querySelector('script')?.dispatchEvent(new Event('load'))
    await loading
  })

  it('preserves encoded pathname segments without decoding them', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')
    const loading = loadOnlyOfficeApi('https://office.example.test/proxy/%2Ftenant///')

    expect(document.querySelector('script')?.src).toBe(
      'https://office.example.test/proxy/%2Ftenant/web-apps/apps/api/documents/api.js',
    )
    window.DocsAPI = { DocEditor: vi.fn() }
    document.querySelector('script')?.dispatchEvent(new Event('load'))
    await loading
  })

  it.each([
    'ftp://office.example.test',
    'https://user:secret@office.example.test',
    'https://office.example.test?tenant=one',
    'https://office.example.test#api',
  ])('rejects an unsafe document server URL: %s', async (baseUrl) => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')

    await expect(loadOnlyOfficeApi(baseUrl)).rejects.toThrow('Invalid ONLYOFFICE document server URL')
    expect(document.querySelectorAll('script')).toHaveLength(0)
  })

  it('rejects a different origin while the singleton API is loading', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')

    const first = loadOnlyOfficeApi('https://office-one.example.test')

    await expect(loadOnlyOfficeApi('https://office-two.example.test')).rejects.toThrow(
      'already belongs to https://office-one.example.test',
    )
    expect(document.querySelectorAll('script')).toHaveLength(1)

    document.querySelector('script')?.dispatchEvent(new Event('error'))
    await expect(first).rejects.toThrow('Failed to load ONLYOFFICE Docs API')
  })

  it('rejects a different proxy base path on the same origin', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')
    const first = loadOnlyOfficeApi('https://office.example.test/onlyoffice-a')

    await expect(loadOnlyOfficeApi('https://office.example.test/onlyoffice-b')).rejects.toThrow(
      'already belongs to https://office.example.test/onlyoffice-a',
    )
    expect(document.querySelectorAll('script')).toHaveLength(1)

    document.querySelector('script')?.dispatchEvent(new Event('error'))
    await expect(first).rejects.toThrow('Failed to load ONLYOFFICE Docs API')
  })

  it('rejects a different origin after the singleton API has loaded', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')
    const first = loadOnlyOfficeApi('https://office-one.example.test')
    window.DocsAPI = { DocEditor: vi.fn() }
    document.querySelector('script')?.dispatchEvent(new Event('load'))
    await first

    await expect(loadOnlyOfficeApi('https://office-two.example.test')).rejects.toThrow(
      'already belongs to https://office-one.example.test',
    )
    expect(document.querySelectorAll('script')).toHaveLength(1)
  })

  it('waits briefly when the load event fires before DocEditor appears', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')
    const loading = loadOnlyOfficeApi('https://office.example.test')

    document.querySelector('script')?.dispatchEvent(new Event('load'))
    window.DocsAPI = { DocEditor: vi.fn() }
    await vi.advanceTimersByTimeAsync(50)

    await expect(loading).resolves.toBe(window.DocsAPI)
  })

  it('bounds readiness waiting, cleans up, and permits a retry', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')
    const failed = loadOnlyOfficeApi('https://office.example.test')

    document.querySelector('script')?.dispatchEvent(new Event('load'))
    const rejection = expect(failed).rejects.toThrow('Timed out waiting for ONLYOFFICE Docs API')
    await vi.advanceTimersByTimeAsync(15_000)
    await rejection
    expect(document.querySelectorAll('script')).toHaveLength(0)

    const retried = loadOnlyOfficeApi('https://office.example.test')
    window.DocsAPI = { DocEditor: vi.fn() }
    document.querySelector('script')?.dispatchEvent(new Event('load'))
    await expect(retried).resolves.toBe(window.DocsAPI)
  })

  it('replaces an unowned pre-existing matching script instead of waiting on a stale tag', async () => {
    const staleScript = document.createElement('script')
    staleScript.src = 'https://office.example.test/web-apps/apps/api/documents/api.js'
    document.head.append(staleScript)
    const { loadOnlyOfficeApi } = await import('./onlyoffice')

    const loading = loadOnlyOfficeApi('https://office.example.test')
    const replacement = document.querySelector('script')

    expect(staleScript.isConnected).toBe(false)
    expect(replacement).not.toBe(staleScript)
    expect(document.querySelectorAll('script')).toHaveLength(1)
    window.DocsAPI = { DocEditor: vi.fn() }
    replacement?.dispatchEvent(new Event('load'))
    await expect(loading).resolves.toBe(window.DocsAPI)
  })

  it('rejects script errors and releases origin ownership for another origin', async () => {
    const { loadOnlyOfficeApi } = await import('./onlyoffice')
    const failed = loadOnlyOfficeApi('https://office-one.example.test')
    document.querySelector('script')?.dispatchEvent(new Event('error'))
    await expect(failed).rejects.toThrow('Failed to load ONLYOFFICE Docs API')

    const retried = loadOnlyOfficeApi('https://office-two.example.test')
    window.DocsAPI = { DocEditor: vi.fn() }
    document.querySelector('script')?.dispatchEvent(new Event('load'))
    await expect(retried).resolves.toBe(window.DocsAPI)
  })
})
