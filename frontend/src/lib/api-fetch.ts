import { clearStoredAuth, getStoredAccessToken, getStoredRefreshToken, updateStoredAccessToken } from './auth'

const nativeFetch = window.fetch.bind(window)

function isAuthEndpoint(input: RequestInfo | URL): boolean {
  const value = typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url
  return value.includes('/api/auth/login') || value.includes('/api/auth/register') || value.includes('/api/auth/refresh')
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getStoredRefreshToken()
  if (!refreshToken) return null

  const response = await nativeFetch('/api/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!response.ok) return null

  const data = await response.json().catch(() => null)
  const accessToken = typeof data?.access_token === 'string' ? data.access_token : null
  if (!accessToken) return null
  updateStoredAccessToken(accessToken)
  return accessToken
}

function redirectToLogin() {
  const next = `${window.location.pathname}${window.location.search}${window.location.hash}`
  if (window.location.pathname !== '/login') {
    window.location.assign(`/login?next=${encodeURIComponent(next)}`)
  }
}

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  // Keep a plain-object snapshot of init so we can retry with a fresh Request
  const initSnapshot = init ? { ...init } : {}
  const request = new Request(input, initSnapshot)
  const headers = new Headers(request.headers)
  const accessToken = getStoredAccessToken()
  if (accessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  let response = await nativeFetch(request, { headers })
  if (response.status !== 401 || isAuthEndpoint(input)) {
    return response
  }

  const refreshedToken = await refreshAccessToken()
  if (!refreshedToken) {
    clearStoredAuth()
    redirectToLogin()
    return response
  }

  // Re-create a fresh Request for the retry; the original request body
  // may have been consumed by the first fetch call.
  const retryRequest = new Request(input, initSnapshot)
  const retryHeaders = new Headers(retryRequest.headers)
  retryHeaders.set('Authorization', `Bearer ${refreshedToken}`)
  response = await nativeFetch(retryRequest, { headers: retryHeaders })
  if (response.status === 401) {
    clearStoredAuth()
    redirectToLogin()
  }
  return response
}

export function installGlobalAuthFetch() {
  const win = window as Window & { __draAuthFetchInstalled?: boolean }
  if (win.__draAuthFetchInstalled) return
  win.__draAuthFetchInstalled = true
  window.fetch = apiFetch as typeof window.fetch
}
