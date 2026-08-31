/** @type {import('tailwindcss').Config} */

// 設計系統(Linear / Vercel 風格的極簡 SaaS)
// ---------------------------------------------------------------------------
// 中性色用 Tailwind 內建 zinc;強調色只有 indigo;語意色 emerald / amber / rose / sky。
// 主題相關的中性色透過 CSS 變數包成語意 token(canvas / surface / ink / hairline …),
// 值定義在 src/index.css:`:root, html.light` 一組、`html.dark` 一組。
// 頁面寫 bg-surface / text-ink-muted / border-hairline 即可自動跟主題,不必到處寫 dark:。
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  // class strategy: ThemeContext 切換 html.dark / html.light
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // 主題感知的中性色 alias
        canvas: token('color-canvas'),
        surface: {
          DEFAULT: token('color-surface'),
          elevated: token('color-surface-elevated'),
          muted: token('color-surface-muted'),
        },
        ink: {
          DEFAULT: token('color-ink'),
          muted: token('color-ink-muted'),
          subtle: token('color-ink-subtle'),
        },
        hairline: {
          DEFAULT: token('color-hairline'),
          strong: token('color-hairline-strong'),
        },
        // 唯一的強調色(light: indigo-600,dark: indigo-500)
        accent: {
          DEFAULT: token('color-accent'),
          hover: token('color-accent-hover'),
          soft: token('color-accent-soft'),
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      borderRadius: {
        DEFAULT: '0.375rem',
      },
      boxShadow: {
        // 只有兩種陰影:控制項的 1px 底影、浮層(dialog / popover)的柔和陰影
        sm: '0 1px 2px 0 rgb(0 0 0 / 0.04)',
        overlay: '0 1px 2px rgb(0 0 0 / 0.06), 0 12px 32px -8px rgb(0 0 0 / 0.18)',
      },
      transitionDuration: {
        DEFAULT: '150ms',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'dialog-in': {
          '0%': { opacity: '0', transform: 'scale(0.98)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'toast-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 150ms ease-out both',
        'dialog-in': 'dialog-in 150ms ease-out both',
        'toast-in': 'toast-in 150ms ease-out both',
      },
    },
  },
  plugins: [],
}
