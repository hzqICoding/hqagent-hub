import { describe, expect, it } from 'vitest'
import { createHash } from 'node:crypto'
import { IncrementalSha256, hashBlob } from './sha256'

describe('bounded incremental SHA-256', () => {
  it.each(['', 'abc', 'a'.repeat(55), 'a'.repeat(56), 'a'.repeat(63), 'a'.repeat(64), 'a'.repeat(65), '文件哈希🙂'.repeat(600)])('matches node SHA-256 across byte boundaries (%#)', (text) => {
    const bytes = new TextEncoder().encode(text)
    const hash = new IncrementalSha256()
    for (let i = 0; i < bytes.length; i += 7) hash.update(bytes.subarray(i, i + 7))
    expect(hash.hex()).toBe(createHash('sha256').update(bytes).digest('hex'))
  })
  it('processes a virtual 20MB file using only bounded slices, without a whole-file read', async () => {
    const size = 20000000
    let calls = 0, largest = 0
    const reference = createHash('sha256')
    const file = { size, arrayBuffer: () => { throw new Error('whole-file read forbidden') }, slice: (start: number, end: number) => {
      const length = Math.min(end, size) - start
      calls++; largest = Math.max(largest, length)
      const bytes = new Uint8Array(length).fill(97); reference.update(bytes)
      return { arrayBuffer: async () => bytes.buffer }
    } } as unknown as Blob
    expect(await hashBlob(file)).toBe(reference.digest('hex'))
    expect(calls).toBe(Math.ceil(size / 65536)); expect(largest).toBeLessThanOrEqual(65536)
  }, 20000)
  it('cancels hashing without processing the rest of a file', async () => {
    const controller = new AbortController(); controller.abort()
    await expect(hashBlob({ size: 1 } as Blob, controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
  })
})
