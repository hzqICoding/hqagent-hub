import { renderSVG } from 'uqr'

/** QR data becomes modules only, never SVG text/attributes. Render as an isolated img,
 * not innerHTML. Fixed colors, M correction and one-module border match the old encoder.
 */
export function pairingQrDataUrl(content: string): string {
  const svg = renderSVG(content, {
    ecc: 'M', boostEcc: false, border: 1, pixelSize: 1,
    blackColor: '#000000', whiteColor: '#ffffff',
  }).replace('<svg ', '<svg width="200" height="200" shape-rendering="crispEdges" ')
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}
