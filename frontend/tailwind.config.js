/** @type {import('tailwindcss').Config} */

// 設計系統「Navy Trust」— Minimalism & Swiss Style,dark-first
// ---------------------------------------------------------------------------
// 所有顏色都是語意 token,值以 CSS 變數定義在 src/index.css:
//   `html.dark`(預設)一組、`html.light` 一組。
// 頁面只寫 bg-card / text-muted-foreground / border-border …,自動跟主題,不必到處寫 dark:。
//
//   background / foreground        頁面底 + 主文字
//   card / popover / muted         卡片、浮層、側欄與表頭底
//   muted-foreground / subtle-foreground   次要文字兩階
//   border / border-strong         分隔線 / 控制項邊框(含透明度的字串,不支援 /alpha)
//   primary                        海軍藍:選中、側欄 active、次要實心按鈕、light 連結
//   accent                         綠色 CTA(每個畫面只有一顆實心綠)
//   link                           文字連結(dark 用綠、light 用海軍藍)
//   destructive                    實心刪除按鈕(#DC2626 + 白字)
//   success / warning / danger / info   語意色(文字、圓點、淡底)
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
        background: token('color-background'),
        foreground: token('color-foreground'),
        card: {
          DEFAULT: token('color-card'),
          foreground: token('color-card-foreground'),
        },
        popover: token('color-popover'),
        muted: {
          DEFAULT: token('color-muted'),
          foreground: token('color-muted-foreground'),
        },
        subtle: {
          foreground: token('color-subtle-foreground'),
        },
        border: {
          DEFAULT: 'var(--color-border)',
          strong: 'var(--color-border-strong)',
        },
        primary: {
          DEFAULT: token('color-primary'),
          hover: token('color-primary-hover'),
          foreground: token('color-primary-foreground'),
          soft: token('color-primary-soft'),
          'soft-foreground': token('color-primary-soft-foreground'),
        },
        accent: {
          DEFAULT: token('color-accent'),
          hover: token('color-accent-hover'),
          foreground: token('color-accent-foreground'),
        },
        link: {
          DEFAULT: token('color-link'),
          hover: token('color-link-hover'),
        },
        destructive: {
          DEFAULT: token('color-destructive'),
          hover: token('color-destructive-hover'),
          foreground: token('color-destructive-foreground'),
        },
        ring: token('color-ring'),
        success: token('color-success'),
        warning: token('color-warning'),
        danger: token('color-danger'),
        info: token('color-info'),
      },
      fontFamily: {
        sans: ['"Fira Sans"', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['"Fira Code"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      borderRadius: {
        // Swiss:小圓角。md = 控制項(6px),lg = 卡片(8px)
        DEFAULT: '0.25rem',
        md: '0.375rem',
        lg: '0.5rem',
        xl: '0.5rem',
      },
      boxShadow: {
        // 卡片不投影;只有浮層(dialog / popover / toast)有一層銳利小陰影
        overlay: '0 1px 2px rgb(0 0 0 / 0.3), 0 8px 24px -8px rgb(0 0 0 / 0.4)',
      },
      transitionDuration: {
        DEFAULT: '200ms',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'dialog-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'toast-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 200ms ease-out both',
        'dialog-in': 'dialog-in 200ms ease-out both',
        'toast-in': 'toast-in 200ms ease-out both',
      },
    },
  },
  plugins: [],
}
