export interface OnlyOfficeEditor {
  destroyEditor(): void
}

export interface OnlyOfficeDocsApi {
  DocEditor: new (
    elementId: string,
    config: Record<string, unknown>,
  ) => OnlyOfficeEditor
}

declare global {
  interface Window {
    DocsAPI?: OnlyOfficeDocsApi
  }
}

const API_PATH = '/web-apps/apps/api/documents/api.js'
const API_READY_TIMEOUT_MS = 10_000
const API_READY_POLL_MS = 25
const SCRIPT_BASE_URL_DATA_KEY = 'slideforgeOnlyofficeBaseUrl'

const apiPromises = new Map<string, Promise<OnlyOfficeDocsApi>>()
let ownedBaseUrl: string | null = null

function canonicalBaseUrl(baseUrl: string): string {
  let parsed: URL
  try {
    parsed = new URL(baseUrl.trim())
  } catch {
    throw new Error('Invalid ONLYOFFICE document server URL')
  }
  if (
    (parsed.protocol !== 'http:' && parsed.protocol !== 'https:')
    || parsed.username
    || parsed.password
    || parsed.href.includes('?')
    || parsed.href.includes('#')
  ) {
    throw new Error('Invalid ONLYOFFICE document server URL')
  }
  const pathname = parsed.pathname.replace(/\/+$/, '')
  return `${parsed.origin}${pathname}`
}

function baseUrlConflict(baseUrl: string): Error {
  return new Error(`ONLYOFFICE Docs API already belongs to ${ownedBaseUrl}; cannot load ${baseUrl}`)
}

export function loadOnlyOfficeApi(baseUrl: string): Promise<OnlyOfficeDocsApi> {
  let normalizedBaseUrl: string
  try {
    normalizedBaseUrl = canonicalBaseUrl(baseUrl)
  } catch (error) {
    return Promise.reject(error)
  }

  if (ownedBaseUrl !== null && ownedBaseUrl !== normalizedBaseUrl) {
    return Promise.reject(baseUrlConflict(normalizedBaseUrl))
  }

  const cached = apiPromises.get(normalizedBaseUrl)
  if (cached) return cached
  ownedBaseUrl = normalizedBaseUrl

  if (window.DocsAPI?.DocEditor) {
    const loaded = Promise.resolve(window.DocsAPI)
    apiPromises.set(normalizedBaseUrl, loaded)
    return loaded
  }

  const scriptUrl = `${normalizedBaseUrl}${API_PATH}`
  const matchingScript = Array.from(document.scripts).find(
    (candidate) => candidate.src === scriptUrl,
  )
  const ownedScript = matchingScript?.dataset[SCRIPT_BASE_URL_DATA_KEY] === normalizedBaseUrl
    ? matchingScript
    : undefined
  if (matchingScript && !ownedScript) matchingScript.remove()

  const script = ownedScript ?? document.createElement('script')
  if (!ownedScript) {
    script.src = scriptUrl
    script.async = true
    script.dataset[SCRIPT_BASE_URL_DATA_KEY] = normalizedBaseUrl
  }

  const loading = new Promise<OnlyOfficeDocsApi>((resolve, reject) => {
    let settled = false

    const cleanup = () => {
      script.removeEventListener('load', checkReady)
      script.removeEventListener('error', handleError)
      window.clearInterval(pollId)
      window.clearTimeout(timeoutId)
    }
    const fail = (error: Error) => {
      if (settled) return
      settled = true
      cleanup()
      apiPromises.delete(normalizedBaseUrl)
      if (ownedBaseUrl === normalizedBaseUrl) ownedBaseUrl = null
      script.remove()
      reject(error)
    }
    const checkReady = () => {
      if (settled || !window.DocsAPI?.DocEditor) return
      settled = true
      cleanup()
      resolve(window.DocsAPI)
    }
    const handleError = () => {
      fail(new Error('Failed to load ONLYOFFICE Docs API'))
    }

    script.addEventListener('load', checkReady)
    script.addEventListener('error', handleError)
    const pollId = window.setInterval(checkReady, API_READY_POLL_MS)
    const timeoutId = window.setTimeout(
      () => fail(new Error('Timed out waiting for ONLYOFFICE Docs API')),
      API_READY_TIMEOUT_MS,
    )
    checkReady()
  })
  apiPromises.set(normalizedBaseUrl, loading)

  if (!ownedScript) document.head.append(script)
  return loading
}
