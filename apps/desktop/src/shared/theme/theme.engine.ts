import { defaultAppearance, type AppearanceSettings, type ResolvedThemeMode } from './theme.types'

const STORAGE_KEY = 'hqagent_appearance'

export class ThemeEngine {
  private static instance: ThemeEngine
  private currentSettings: AppearanceSettings = { ...defaultAppearance }
  private darkModeMediaQuery: MediaQueryList | null = null
  private motionMediaQuery: MediaQueryList | null = null
  private listeners: Set<(settings: AppearanceSettings) => void> = new Set()

  private constructor() {
    this.setupMediaQueries()
  }

  public static getInstance(): ThemeEngine {
    if (!ThemeEngine.instance) {
      ThemeEngine.instance = new ThemeEngine()
    }
    return ThemeEngine.instance
  }

  private setupMediaQueries() {
    if (typeof window === 'undefined' || !window.matchMedia) return

    this.darkModeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    this.motionMediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')

    const onSystemDarkChange = () => {
      if (this.currentSettings.mode === 'system') {
        this.applyToDom()
        this.notify()
      }
    }

    const onSystemMotionChange = () => {
      if (this.currentSettings.reduceMotion === 'system') {
        this.applyToDom()
        this.notify()
      }
    }

    if (this.darkModeMediaQuery.addEventListener) {
      this.darkModeMediaQuery.addEventListener('change', onSystemDarkChange)
      this.motionMediaQuery.addEventListener('change', onSystemMotionChange)
    } else {
      // Fallback for older browsers
      this.darkModeMediaQuery.addListener(onSystemDarkChange)
      this.motionMediaQuery.addListener(onSystemMotionChange)
    }
  }

  public init(initial?: Partial<AppearanceSettings>): AppearanceSettings {
    let saved: Partial<AppearanceSettings> = {}
    try {
      const cached = localStorage.getItem(STORAGE_KEY)
      if (cached) {
        saved = JSON.parse(cached)
      }
    } catch (e) {
      console.warn('[ThemeEngine] Failed to load cached settings', e)
    }

    this.currentSettings = {
      ...defaultAppearance,
      ...saved,
      ...initial,
    }

    this.applyToDom()
    return this.currentSettings
  }

  public getSettings(): AppearanceSettings {
    return { ...this.currentSettings }
  }

  public getResolvedMode(): ResolvedThemeMode {
    if (this.currentSettings.mode === 'system') {
      return this.darkModeMediaQuery?.matches ? 'dark' : 'light'
    }
    return this.currentSettings.mode
  }

  public updateSettings(partial: Partial<AppearanceSettings>): AppearanceSettings {
    this.currentSettings = {
      ...this.currentSettings,
      ...partial,
    }

    this.persist()
    this.applyToDom()
    this.notify()
    return this.getSettings()
  }

  private applyToDom() {
    if (typeof document === 'undefined') return
    const root = document.documentElement
    const resolvedMode = this.getResolvedMode()
    const resolvedMotion =
      this.currentSettings.reduceMotion === 'system'
        ? Boolean(this.motionMediaQuery?.matches)
        : Boolean(this.currentSettings.reduceMotion)

    root.setAttribute('data-theme-mode', resolvedMode)
    root.setAttribute('data-theme-source', this.currentSettings.mode)
    root.setAttribute('data-theme-palette', this.currentSettings.palette)
    root.setAttribute('data-density', this.currentSettings.density)
    root.setAttribute('data-contrast', this.currentSettings.contrast)
    root.setAttribute('data-reduce-motion', String(resolvedMotion))
    root.style.setProperty('--font-scale', String(this.currentSettings.fontScale || 1))
  }

  private persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.currentSettings))
    } catch (e) {
      console.warn('[ThemeEngine] Failed to persist settings', e)
    }
  }

  public subscribe(listener: (settings: AppearanceSettings) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private notify() {
    const s = this.getSettings()
    this.listeners.forEach((fn) => fn(s))
  }
}

export const themeEngine = ThemeEngine.getInstance()
