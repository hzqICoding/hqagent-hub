import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  darkMode: ['class', '[data-theme-mode="dark"]'],
  theme: {
    extend: {
      colors: {
        app: 'var(--color-bg-app)',
        sidebar: 'var(--color-bg-sidebar)',
        panel: 'var(--color-bg-panel)',
        elevated: 'var(--color-bg-elevated)',
        muted: 'var(--color-bg-muted)',
        code: 'var(--color-bg-code)',
        border: {
          subtle: 'var(--color-border-subtle)',
          DEFAULT: 'var(--color-border-default)',
          strong: 'var(--color-border-strong)',
        },
        content: {
          primary: 'var(--color-text-primary)',
          secondary: 'var(--color-text-secondary)',
          muted: 'var(--color-text-muted)',
          disabled: 'var(--color-text-disabled)',
        },
        action: {
          primary: 'var(--color-action-primary)',
          'primary-hover': 'var(--color-action-primary-hover)',
          'primary-active': 'var(--color-action-primary-active)',
          'primary-text': 'var(--color-action-primary-text)',
        },
        primary: {
          DEFAULT: 'var(--color-action-primary)',
          50: 'var(--color-accent-soft)',
          100: 'var(--color-accent-soft)',
          500: 'var(--color-accent)',
          600: 'var(--color-action-primary)',
          700: 'var(--color-action-primary-hover)',
          800: 'var(--color-action-primary-active)',
          900: 'var(--color-action-primary-active)',
          950: 'var(--color-accent-soft)',
        },
        accent: {
          DEFAULT: 'var(--color-accent)',
          soft: 'var(--color-accent-soft)',
        },
        ring: {
          DEFAULT: 'var(--color-focus-ring)',
        },
        status: {
          success: 'var(--color-status-success)',
          'success-soft': 'var(--color-status-success-soft)',
          warning: 'var(--color-status-warning)',
          'warning-soft': 'var(--color-status-warning-soft)',
          danger: 'var(--color-status-danger)',
          'danger-soft': 'var(--color-status-danger-soft)',
          info: 'var(--color-status-info)',
          'info-soft': 'var(--color-status-info-soft)',
          neutral: 'var(--color-status-neutral)',
          'neutral-soft': 'var(--color-status-neutral-soft)',
        },
        role: {
          orchestrator: 'var(--role-orchestrator)',
          architect: 'var(--role-architect)',
          frontend: 'var(--role-frontend)',
          implementer: 'var(--role-implementer)',
          reviewer: 'var(--role-reviewer)',
          tester: 'var(--role-tester)',
          deployer: 'var(--role-deployer)',
          integrator: 'var(--role-integrator)',
        },
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
      },
      boxShadow: {
        panel: 'var(--shadow-panel)',
        popover: 'var(--shadow-popover)',
      },
    },
  },
  plugins: [],
} satisfies Config
