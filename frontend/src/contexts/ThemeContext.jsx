import { createContext, useContext, useState, useEffect } from 'react'

const ThemeContext = createContext()

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

export function ThemeProvider({ children }) {
  // Dark 是預設與設計基準;只有使用者明確選過 light 才用淺色。
  // 用新的 key(mcp-theme):舊版會把自動算出的預設值也寫進 'theme',不能當成使用者的選擇。
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('mcp-theme')
    return saved === 'light' ? 'light' : 'dark'
  })

  // Update document class and localStorage when theme changes
  useEffect(() => {
    const root = document.documentElement

    if (theme === 'light') {
      root.classList.add('light')
      root.classList.remove('dark')
    } else {
      root.classList.add('dark')
      root.classList.remove('light')
    }

  }, [theme])

  // 只有使用者親手切換才持久化
  const toggleTheme = () => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark'
      try { localStorage.setItem('mcp-theme', next) } catch { /* storage 不可用時靜默 */ }
      return next
    })
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
