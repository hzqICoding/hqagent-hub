import { describe, expect, it } from 'vitest'
const sources = import.meta.glob('../../**/*.{vue,ts}', { eager:true, query:'?raw', import:'default' }) as Record<string,string>
describe('shared mobile interaction contract', () => {
  it('has no native window confirmation, alert or prompt calls in application sources', () => {
    const violations = Object.entries(sources).filter(([path,text]) => !/\.(test|spec)\.ts$/.test(path) && /\bwindow\s*\.\s*(confirm|alert|prompt)\s*\(/.test(text)).map(([path])=>path)
    expect(violations).toEqual([])
  })
  it('has no native mobile select elements', () => {
    const violations = Object.entries(sources).filter(([path,text])=> (path.includes('/pages/remote/') || path.endsWith('/RemoteWorkspaceDialog.vue')) && path.endsWith('.vue') && /<select\b/.test(text)).map(([path])=>path)
    expect(violations).toEqual([])
  })
})
