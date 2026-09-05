export type {
  ThemeMode,
  ResolvedThemeMode,
  ThemePalette,
  UiDensity,
  ContrastMode,
  FontScale,
  AppearanceSettings,
} from '@hqagent/protocol'

export { defaultAppearance } from '@hqagent/protocol'

export const PALETTES_META: Record<
  string,
  { id: string; name: string; primaryHex: string; darkAccentHex: string; description: string }
> = {
  'hq-blue': {
    id: 'hq-blue',
    name: 'HQ Blue (默认)',
    primaryHex: '#2563EB',
    darkAccentHex: '#60A5FA',
    description: '专业、稳定，适合长时间桌面工程使用',
  },
  'ai-violet': {
    id: 'ai-violet',
    name: 'AI Violet (紫罗兰)',
    primaryHex: '#6D28D9',
    darkAccentHex: '#A78BFA',
    description: '借鉴 AI-Native 与 Bento 设计，突出 AI 生产力质感',
  },
  'tech-cyan': {
    id: 'tech-cyan',
    name: 'Tech Cyan (科技青)',
    primaryHex: '#0E7490',
    darkAccentHex: '#22D3EE',
    description: '工程监控与技术硬核风格',
  },
  'ops-emerald': {
    id: 'ops-emerald',
    name: 'Ops Emerald (运维绿)',
    primaryHex: '#047857',
    darkAccentHex: '#34D399',
    description: '借鉴实时健康与运维大屏，突出可信与就绪状态',
  },
}
