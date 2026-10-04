// One immutable capability set for lists, writes, polling, binary transport and WS tickets.
// Cursors live in memory; a fresh client starts with fresh snapshots and tickets.
export const CLIENT_FEATURE_HEADER = 'X-HQ-Client-Features'
export const CLIENT_FEATURES = 'pi-v1'
export function clientFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  if (init.headers instanceof Headers) {
    const headers = new Headers(init.headers); headers.set(CLIENT_FEATURE_HEADER, CLIENT_FEATURES)
    return fetch(input, { ...init, headers })
  }
  const headers: Record<string,string> = Array.isArray(init.headers) ? Object.fromEntries(init.headers) : { ...init.headers }
  for (const key of Object.keys(headers)) if (key.toLowerCase() === CLIENT_FEATURE_HEADER.toLowerCase()) delete headers[key]
  headers[CLIENT_FEATURE_HEADER] = CLIENT_FEATURES
  return fetch(input, { ...init, headers })
}
export function applyClientFeatures(xhr: Pick<XMLHttpRequest, 'setRequestHeader'>) { xhr.setRequestHeader(CLIENT_FEATURE_HEADER, CLIENT_FEATURES) }
