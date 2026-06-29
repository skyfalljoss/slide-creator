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

const apiPromises = new Map<string, Promise<OnlyOfficeDocsApi>>()

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, '')
}

export function loadOnlyOfficeApi(baseUrl: string): Promise<OnlyOfficeDocsApi> {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl)
  const cached = apiPromises.get(normalizedBaseUrl)
  if (cached) return cached

  if (window.DocsAPI?.DocEditor) {
    const loaded = Promise.resolve(window.DocsAPI)
    apiPromises.set(normalizedBaseUrl, loaded)
    return loaded
  }

  const scriptUrl = `${normalizedBaseUrl}/web-apps/apps/api/documents/api.js`
  const existingScript = Array.from(document.scripts).find(
    (script) => script.src === scriptUrl,
  )
  const script = existingScript ?? document.createElement('script')

  const loading = new Promise<OnlyOfficeDocsApi>((resolve, reject) => {
    const cleanup = () => {
      script.removeEventListener('load', handleLoad)
      script.removeEventListener('error', handleError)
    }
    const fail = (error: Error) => {
      cleanup()
      apiPromises.delete(normalizedBaseUrl)
      script.remove()
      reject(error)
    }
    const handleLoad = () => {
      if (!window.DocsAPI?.DocEditor) {
        fail(new Error('ONLYOFFICE Docs API did not expose DocsAPI.DocEditor'))
        return
      }
      cleanup()
      resolve(window.DocsAPI)
    }
    const handleError = () => {
      fail(new Error('Failed to load ONLYOFFICE Docs API'))
    }

    script.addEventListener('load', handleLoad)
    script.addEventListener('error', handleError)
  })
  apiPromises.set(normalizedBaseUrl, loading)

  if (!existingScript) {
    script.src = scriptUrl
    script.async = true
    document.head.append(script)
  }

  return loading
}
