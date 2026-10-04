import { describe, expect, it } from 'vitest'
import { renderSVG } from 'uqr'
import { pairingQrDataUrl } from './pairing-qr-code'

describe('controlled pairing QR SVG', () => {
  it('retains M correction, a one-module margin, fixed colors and an isolated image URL', () => {
    const content='https://example.invalid/remote/pair#code=ABCD2345'
    const url=pairingQrDataUrl(content)
    expect(url.startsWith('data:image/svg+xml;charset=utf-8,')).toBe(true)
    expect(decodeURIComponent(url.split(',')[1]).replace(' width="200" height="200" shape-rendering="crispEdges"','')).toBe(renderSVG(content,{ecc:'M',boostEcc:false,border:1,pixelSize:1,blackColor:'#000000',whiteColor:'#ffffff'}))
  })
  it('cannot turn encoded input into SVG markup, attributes, references or scripts', () => {
    const svg=decodeURIComponent(pairingQrDataUrl('<svg onload="UNTRUSTED_MARKER"><script>UNTRUSTED_MARKER</script>javascript:UNTRUSTED_MARKER').split(',')[1])
    const document=new DOMParser().parseFromString(svg,'image/svg+xml')
    expect([...document.querySelectorAll('*')].map(node=>node.tagName)).toEqual(['svg','rect','path'])
    expect(svg).not.toContain('UNTRUSTED_MARKER')
    expect(document.querySelector('path')?.getAttribute('d')).toMatch(/^[Mhvz,0-9-]+$/)
    expect([...document.querySelectorAll('*')].flatMap(node=>[...node.attributes].map(attr=>attr.name)).every(name=>['xmlns','viewBox','width','height','shape-rendering','fill','d'].includes(name))).toBe(true)
  })
})
