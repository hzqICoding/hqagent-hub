import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { themeEngine } from './theme.engine'
import type {
  AppearanceSettings,
  ThemeMode,
  ThemePalette,
  UiDensity,
  ContrastMode,
  FontScale,
  ReduceMotion,
} from './theme.types'

export const useThemeStore = defineStore('theme', () => {
  const settings = ref<AppearanceSettings>(themeEngine.getSettings())

  themeEngine.subscribe((newSettings) => {
    settings.value = { ...newSettings }
  })

  const mode = computed(() => settings.value.mode)
  const resolvedMode = computed(() => themeEngine.getResolvedMode())
  const palette = computed(() => settings.value.palette)
  const density = computed(() => settings.value.density)
  const contrast = computed(() => settings.value.contrast)
  const fontScale = computed(() => settings.value.fontScale)
  const isDark = computed(() => resolvedMode.value === 'dark')

  function setMode(newMode: ThemeMode) {
    settings.value = themeEngine.updateSettings({ mode: newMode })
  }

  function setPalette(newPalette: ThemePalette) {
    settings.value = themeEngine.updateSettings({ palette: newPalette })
  }

  function setDensity(newDensity: UiDensity) {
    settings.value = themeEngine.updateSettings({ density: newDensity })
  }

  function setContrast(newContrast: ContrastMode) {
    settings.value = themeEngine.updateSettings({ contrast: newContrast })
  }

  function setFontScale(newScale: FontScale) {
    settings.value = themeEngine.updateSettings({ fontScale: newScale })
  }

  function setReduceMotion(reduce: ReduceMotion) {
    settings.value = themeEngine.updateSettings({ reduceMotion: reduce })
  }

  function updateAll(newSettings: Partial<AppearanceSettings>) {
    settings.value = themeEngine.updateSettings(newSettings)
  }

  return {
    settings,
    mode,
    resolvedMode,
    palette,
    density,
    contrast,
    fontScale,
    isDark,
    setMode,
    setPalette,
    setDensity,
    setContrast,
    setFontScale,
    setReduceMotion,
    updateAll,
  }
})
