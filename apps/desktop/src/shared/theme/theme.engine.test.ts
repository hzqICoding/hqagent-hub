import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ThemeEngine } from './theme.engine'

describe('ThemeEngine', () => {
  let engine: ThemeEngine

  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme-mode')
    document.documentElement.removeAttribute('data-theme-palette')
    document.documentElement.removeAttribute('data-density')
    document.documentElement.removeAttribute('data-contrast')

    // Mock matchMedia
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: query.includes('dark') ? false : false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    engine = ThemeEngine.getInstance()
  })

  it('initializes with default appearance', () => {
    const settings = engine.init()
    expect(settings.mode).toBe('system')
    expect(settings.palette).toBe('hq-blue')
    expect(settings.density).toBe('comfortable')
    expect(document.documentElement.getAttribute('data-theme-palette')).toBe('hq-blue')
  })

  it('switches mode and updates DOM attributes', () => {
    engine.updateSettings({ mode: 'dark' })
    expect(document.documentElement.getAttribute('data-theme-mode')).toBe('dark')

    engine.updateSettings({ mode: 'light' })
    expect(document.documentElement.getAttribute('data-theme-mode')).toBe('light')
  })

  it('switches palette across 4 themes', () => {
    const palettes = ['hq-blue', 'ai-violet', 'tech-cyan', 'ops-emerald'] as const
    for (const p of palettes) {
      engine.updateSettings({ palette: p })
      expect(document.documentElement.getAttribute('data-theme-palette')).toBe(p)
    }
  })

  it('switches density between comfortable and compact', () => {
    engine.updateSettings({ density: 'compact' })
    expect(document.documentElement.getAttribute('data-density')).toBe('compact')

    engine.updateSettings({ density: 'comfortable' })
    expect(document.documentElement.getAttribute('data-density')).toBe('comfortable')
  })

  it('persists settings to localStorage', () => {
    engine.updateSettings({ palette: 'ai-violet', density: 'compact' })
    const stored = JSON.parse(localStorage.getItem('hqagent_appearance') || '{}')
    expect(stored.palette).toBe('ai-violet')
    expect(stored.density).toBe('compact')
  })
})
