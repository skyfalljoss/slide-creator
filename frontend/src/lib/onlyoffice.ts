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
const SCRIPT_ORIGIN_DATA_KEY = 'slideforgeOnlyofficeOrigin'

const apiPromises = new Map<string, Promise<OnlyOfficeDocsApi>>()
let ownedOrigin: string | null = null

function canonicalOrigin(baseUrl: string): string {
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
  // The Docs API is server-wide, so configured paths are intentionally ignored.
  return parsed.origin
}

function originConflict(origin: string): Error {
  return new Error(`ONLYOFFICE Docs API already belongs to ${ownedOrigin}; cannot load ${origin}`)
}

export function loadOnlyOfficeApi(baseUrl: string): Promise<OnlyOfficeDocsApi> {
  let origin: string
  try {
    origin = canonicalOrigin(baseUrl)
  } catch (error) {
    return Promise.reject(error)
  }

  if (ownedOrigin !== null && ownedOrigin !== origin) {
    return Promise.reject(originConflict(origin))
  }

  const cached = apiPromises.get(origin)
  if (cached) return cached
  ownedOrigin = origin

  if (window.DocsAPI?.DocEditor) {
    const loaded = Promise.resolve(window.DocsAPI)
    apiPromises.set(origin, loaded)
    return loaded
  }

  const scriptUrl = `${origin}${API_PATH}`
  const matchingScript = Array.from(document.scripts).find(
    (candidate) => candidate.src === scriptUrl,
  )
  const ownedScript = matchingScript?.dataset[SCRIPT_ORIGIN_DATA_KEY] === origin
    ? matchingScript
    : undefined
  if (matchingScript && !ownedScript) matchingScript.remove()

  const script = ownedScript ?? document.createElement('script')
  if (!ownedScript) {
    script.src = scriptUrl
    script.async = true
    script.dataset[SCRIPT_ORIGIN_DATA_KEY] = origin
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
      apiPromises.delete(origin)
      if (ownedOrigin === origin) ownedOrigin = null
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
  apiPromises.set(origin, loading)

  if (!ownedScript) document.head.append(script)
  return loading
}
