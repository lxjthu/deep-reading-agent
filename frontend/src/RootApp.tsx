import { useEffect, useMemo, useState } from 'react'
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom'
import AdminPage from './AdminPage'
import WorkspaceApp from './App'
import { installGlobalAuthFetch } from './lib/api-fetch'
import { type AuthUser } from './lib/auth'
import { useAuthStore } from './store/auth'

type AuthFormProps = {
  title: string
  subtitle: string
  footer: React.ReactNode
  onSubmit: (payload: {
    username: string
    email?: string
    password: string
    invite_code?: string
  }) => Promise<void>
  mode: 'login' | 'register'
}

const PASSWORD_RULE_TEXT = '密码必须至少 8 位，且同时包含字母和数字。'

function isStrongPassword(password: string) {
  return password.length >= 8 && /[A-Za-z]/.test(password) && /\d/.test(password)
}

function AuthLayout({ title, subtitle, footer, onSubmit, mode }: AuthFormProps) {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-10">
      <div className="mx-auto max-w-md rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
        <div className="mb-6 text-center">
          <div className="mb-3 text-3xl">❤️‍🔥</div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          <p className="mt-2 text-sm text-gray-500">{subtitle}</p>
        </div>

        <form
          className="space-y-4"
          onSubmit={async (event) => {
            event.preventDefault()
            setLoading(true)
            setError('')
            try {
              if (mode === 'register' && password !== confirmPassword) {
                throw new Error('两次输入的密码不一致。')
              }
              if (mode === 'register' && !isStrongPassword(password)) {
                throw new Error(PASSWORD_RULE_TEXT)
              }
              await onSubmit({
                username,
                email: email || undefined,
                password,
                invite_code: inviteCode || undefined,
              })
            } catch (submitError: any) {
              setError(submitError.message || '操作失败。')
            } finally {
              setLoading(false)
            }
          }}
        >
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">用户名</label>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              placeholder="请输入用户名"
              required
            />
          </div>

          {mode === 'register' && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">邮箱</label>
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                placeholder="可选，用于找回或联系"
                type="email"
              />
            </div>
          )}

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">密码</label>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              placeholder="请输入密码"
              type="password"
              required
              minLength={mode === 'register' ? 8 : undefined}
            />
            {mode === 'register' && (
              <p className="mt-1 text-xs text-gray-500">{PASSWORD_RULE_TEXT}</p>
            )}
          </div>

          {mode === 'register' && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">确认密码</label>
              <input
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                placeholder="请再次输入密码"
                type="password"
                required
              />
            </div>
          )}

          {mode === 'register' && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">邀请码</label>
              <input
                value={inviteCode}
                onChange={(event) => setInviteCode(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                placeholder="可选，填写后可注册 VIP"
              />
            </div>
          )}

          {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}

          <button
            disabled={loading}
            className="w-full rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2.5 text-sm font-medium text-white hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50"
            type="submit"
          >
            {loading ? '处理中...' : mode === 'login' ? '登录' : '注册并进入工作台'}
          </button>
        </form>

        <div className="mt-5 text-center text-sm text-gray-500">{footer}</div>
      </div>
    </div>
  )
}

function buildWorkspaceRedirect(user: AuthUser | null, currentSearch: string) {
  const tabSearch = currentSearch ? currentSearch : ''
  if (!user) return '/login'
  return `/workspace${tabSearch}`
}

function HomeRedirect() {
  const { initialized, user } = useAuthStore()
  const location = useLocation()
  if (!initialized) return null
  return <Navigate replace to={buildWorkspaceRedirect(user, location.search)} />
}

function ProtectedRoute() {
  const { initialized, accessToken } = useAuthStore()
  const location = useLocation()
  if (!initialized) return null
  if (!accessToken) {
    const next = `${location.pathname}${location.search}${location.hash}`
    return <Navigate replace to={`/login?next=${encodeURIComponent(next)}`} />
  }
  return <Outlet />
}

function AdminRoute() {
  const { user } = useAuthStore()
  if (!user) return <Navigate replace to="/login" />
  if (user.role !== 'admin') {
    return (
      <div className="min-h-screen bg-gray-50 px-4 py-10">
        <div className="mx-auto max-w-lg rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
          <h1 className="text-xl font-bold text-gray-900">403</h1>
          <p className="mt-3 text-sm text-gray-600">当前账号不是管理员，暂时不能访问后台页面。</p>
        </div>
      </div>
    )
  }
  return <AdminPage />
}

function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { login, accessToken } = useAuthStore()
  const next = useMemo(() => searchParams.get('next') || '/workspace', [searchParams])

  useEffect(() => {
    if (accessToken) return
    let cancelled = false
    const autoLoginPackagedAdmin = async () => {
      try {
        const runtimeResponse = await fetch('/api/deploy/runtime')
        if (!runtimeResponse.ok) return
        const runtime = await runtimeResponse.json()
        if (!runtime?.packaged) return
        await login({ username: 'admin', password: 'admin12345' })
        if (!cancelled) {
          navigate(next, { replace: true })
        }
      } catch {
        // Keep the normal login form available if packaged auto-login fails.
      }
    }
    void autoLoginPackagedAdmin()
    return () => {
      cancelled = true
    }
  }, [accessToken, login, navigate, next])

  useEffect(() => {
    if (accessToken) {
      navigate(next, { replace: true })
    }
  }, [accessToken, navigate, next])

  return (
    <AuthLayout
      title="登录 Deep Reading Agent"
      subtitle="登录后进入多用户工作台"
      mode="login"
      onSubmit={async ({ username, password }) => {
        await login({ username, password })
        navigate(next, { replace: true })
      }}
      footer={
        <span>
          还没有账号？
          <a className="ml-1 font-medium text-emerald-600 hover:text-emerald-700" href="/register">
            去注册
          </a>
        </span>
      }
    />
  )
}

function RegisterPage() {
  const navigate = useNavigate()
  const { register, accessToken } = useAuthStore()

  useEffect(() => {
    if (accessToken) {
      navigate('/workspace', { replace: true })
    }
  }, [accessToken, navigate])

  return (
    <AuthLayout
      title="注册 Deep Reading Agent"
      subtitle="支持普通注册，也支持邀请码注册 VIP"
      mode="register"
      onSubmit={async ({ username, email, password, invite_code }) => {
        await register({ username, email, password, invite_code })
        navigate('/workspace', { replace: true })
      }}
      footer={
        <span>
          已有账号？
          <a className="ml-1 font-medium text-emerald-600 hover:text-emerald-700" href="/login">
            去登录
          </a>
        </span>
      }
    />
  )
}

function AppRoutes() {
  const hydrate = useAuthStore((state) => state.hydrate)

  useEffect(() => {
    installGlobalAuthFetch()
    hydrate()
  }, [hydrate])

  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/workspace/*" element={<WorkspaceApp />} />
        <Route path="/admin" element={<AdminRoute />} />
      </Route>
      <Route path="*" element={<Navigate replace to="/" />} />
    </Routes>
  )
}

export default function RootApp() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
