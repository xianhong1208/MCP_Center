import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import { rememberRedirect } from './utils/redirect'
import Layout from './components/Layout'
import Spinner from './components/ui/Spinner'
import LoginPage from './pages/LoginPage'
import SetupPage from './pages/SetupPage'
import ConsentPage from './pages/ConsentPage'
import DashboardPage from './pages/DashboardPage'
import TokensPage from './pages/TokensPage'
import TokenDetailPage from './pages/TokenDetailPage'
import CreateTokenPage from './pages/CreateTokenPage'
import ServicesPage from './pages/ServicesPage'
import ServiceDetailPage from './pages/ServiceDetailPage'
import OAuthClientsPage from './pages/OAuthClientsPage'
import MarketplacePage from './pages/MarketplacePage'
import AuditLogPage from './pages/AuditLogPage'

function FullScreenSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-subtle-foreground">
      <Spinner size="lg" />
    </div>
  )
}

/**
 * 未登入 → 記住目前位置再去 /login。
 * 這對 OAuth 流程至關重要:後端把未登入的瀏覽器導到 /consent?rid=...,
 * 登入(含 GitHub / Google)之後必須回到同一個同意頁,授權請求才接得上。
 */
function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return <FullScreenSpinner />

  if (!isAuthenticated) {
    rememberRedirect(location.pathname + location.search)
    return <Navigate to="/login" replace />
  }

  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/setup" element={<SetupPage />} />
      <Route
        path="/consent"
        element={
          <ProtectedRoute>
            <ConsentPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="services" element={<ServicesPage />} />
        <Route path="services/:serviceId" element={<ServiceDetailPage />} />
        <Route path="tokens" element={<TokensPage />} />
        <Route path="tokens/create" element={<CreateTokenPage />} />
        <Route path="tokens/:jti" element={<TokenDetailPage />} />
        <Route path="clients" element={<OAuthClientsPage />} />
        <Route path="marketplace" element={<MarketplacePage />} />
        <Route path="audit" element={<AuditLogPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
