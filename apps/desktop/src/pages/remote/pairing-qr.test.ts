import { describe, expect, it } from 'vitest'
import { parsePairingQr } from './pairing-qr'

const origin = 'https://pair.example.invalid'
describe('same-origin pairing QR parser', () => {
  it.each([
    ['ABCD1234', 'ABCD1234'], [' abcd1234 ', 'ABCD1234'],
    [`${origin}/remote/pair#code=abcd1234`, 'ABCD1234'],
    [`${origin}:443/remote/pair#code=ABCD1234`, 'ABCD1234'],
    [`${origin}/remote/pair#other=value&code=ABCD1234`, 'ABCD1234'],
  ])('accepts a valid code or matching service link (%#)', (raw, code) => {
    expect(parsePairingQr(raw, origin)).toBe(code)
  })
  it.each([
    'https://outside.invalid/remote/pair#code=ABCD1234',
    'https://pair.example.invalid.evil.invalid/remote/pair#code=ABCD1234',
    `${origin}:444/remote/pair#code=ABCD1234`,
    'http://pair.example.invalid/remote/pair#code=ABCD1234',
    `${origin}/remote/chat#code=ABCD1234`, `${origin}/remote/pair/#code=ABCD1234`,
    `${origin}/remote/pair`, `${origin}/remote/pair#notcode=ABCD1234`,
    `${origin}/remote/pair#code=ABC-1234`, `${origin}/remote/pair#code=ABCD12345`,
    `${origin}/remote/pair#code=ABCD1234&code=ZZZZ1234`,
    `${origin}/remote/pair?code=ABCD1234`, `${origin}/remote/pair?extra=1#code=ABCD1234`,
    'https://user:pass@pair.example.invalid/remote/pair#code=ABCD1234',
    'javascript:alert(1)', 'data:text/plain,ABCD1234', '//pair.example.invalid/remote/pair#code=ABCD1234',
    '/remote/pair#code=ABCD1234', 'hello world', 'ＡBCD1234', 'ABCD-123', 'ABCD\n1234',
    `${origin}/remote/pa\nir#code=ABCD1234`, 'a'.repeat(2049),
  ])('rejects unrelated or malformed content (%#)', (raw) => {
    expect(parsePairingQr(raw, origin)).toBeNull()
  })
})
