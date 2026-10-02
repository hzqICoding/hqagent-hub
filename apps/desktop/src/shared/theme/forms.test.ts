import { describe, expect, it } from 'vitest'

const components = import.meta.glob('../../**/*.vue', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>
describe('shared native control theme coverage', () => {
  it('keeps every native editable input/textarea/select on the shared control contract', () => {
    const missing: string[] = []
    let fields = 0
    for (const [name, source] of Object.entries(components)) {
      const tags = source.match(/<(?:input|textarea|select)\b(?:"[^"]*"|'[^']*'|[^'">])*>/gs) || []
      for (const tag of tags) {
        const type = tag.match(/(?<![:\w-])type=["']([^"']+)/)?.[1]
        if (type && ['checkbox','radio','range','color','hidden','file','submit','button','reset','image'].includes(type)) continue
        fields++
        if (!tag.includes('hq-form-control')) missing.push(name)
      }
    }
    expect(fields).toBeGreaterThan(35)
    expect(missing).toEqual([])
  })
})
