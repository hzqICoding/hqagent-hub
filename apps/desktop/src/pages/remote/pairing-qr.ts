/** Accept only this service's pairing link or the protocol's 8 ASCII alphanumerics.
 * The decoded string is never navigated to, logged, persisted or put in a query. */
export function parsePairingQr(raw: string, currentOrigin: string): string | null {
  if (typeof raw !== 'string' || raw.length > 2048) return null
  const value = raw.trim()
  if (/^[A-Za-z0-9]{8}$/.test(value)) return value.toUpperCase()
  if (/\s/.test(value)) return null
  try {
    const url = new URL(value)
    const origin = new URL(currentOrigin).origin
    if (!['https:', 'http:'].includes(url.protocol) || url.origin !== origin || url.username || url.password || url.pathname !== '/remote/pair' || url.search) return null
    const codes = new URLSearchParams(url.hash.slice(1)).getAll('code')
    return codes.length === 1 && /^[A-Za-z0-9]{8}$/.test(codes[0]) ? codes[0].toUpperCase() : null
  } catch { return null }
}
