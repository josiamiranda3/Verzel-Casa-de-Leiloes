import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AuditPage, AuctioneerPage, MyWinsPage, ReceiptPage, WalletPage } from './PortalPages.tsx'

const path = window.location.pathname
const page = path === '/wallet' ? <WalletPage />
  : path === '/auctioneer' ? <AuctioneerPage />
  : path === '/my-wins' ? <MyWinsPage />
  : /^\/lots\/\d+\/receipt\/?$/.test(path) ? <ReceiptPage />
  : /^\/audit\/lots\/\d+\/?$/.test(path) ? <AuditPage />
  : <App />

const THEME_KEY = 'verzel_theme'

type Theme = 'light' | 'dark'

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = window.localStorage.getItem(THEME_KEY)
      if (saved === 'dark' || saved === 'light') return saved
    } catch {
      // A preferência do sistema continua disponível se o armazenamento estiver bloqueado.
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    try {
      window.localStorage.setItem(THEME_KEY, theme)
    } catch {
      // O modo continua funcionando durante a sessão mesmo sem localStorage.
    }
  }, [theme])

  return (
    <button
      className="theme-toggle"
      type="button"
      aria-label={theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro'}
      title={theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro'}
      aria-pressed={theme === 'dark'}
      onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')}
    >
      <span aria-hidden="true">{theme === 'dark' ? '☀' : '☾'}</span>
      <span className="theme-toggle-label">{theme === 'dark' ? 'Modo claro' : 'Modo escuro'}</span>
    </button>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeToggle />
    {page}
  </StrictMode>,
)
