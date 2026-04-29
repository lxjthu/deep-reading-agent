(function () {
  const ACCESS_TOKEN_KEY = 'dra_access_token'
  const REFRESH_TOKEN_KEY = 'dra_refresh_token'

  const nativeFetch = window.fetch.bind(window)

  function getAccessToken() {
    return localStorage.getItem(ACCESS_TOKEN_KEY)
  }

  function getRefreshToken() {
    return localStorage.getItem(REFRESH_TOKEN_KEY)
  }

  function clearAuth() {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    localStorage.removeItem('dra_user')
  }

  async function refreshAccessToken() {
    const refreshToken = getRefreshToken()
    if (!refreshToken) return null

    const response = await nativeFetch('/api/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!response.ok) return null

    const data = await response.json().catch(() => null)
    if (!data || typeof data.access_token !== 'string') return null
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
    return data.access_token
  }

  function redirectToLogin() {
    const next = window.location.pathname + window.location.search + window.location.hash
    if (window.top) {
      window.top.location.href = '/login?next=' + encodeURIComponent('/workspace?tab=compare')
      return
    }
    window.location.href = '/login?next=' + encodeURIComponent(next)
  }

  async function authFetch(input, init) {
    const headers = new Headers((init && init.headers) || {})
    const accessToken = getAccessToken()
    if (accessToken && !headers.has('Authorization')) {
      headers.set('Authorization', 'Bearer ' + accessToken)
    }

    let response = await nativeFetch(input, { ...(init || {}), headers })
    if (response.status !== 401) return response

    const refreshedToken = await refreshAccessToken()
    if (!refreshedToken) {
      clearAuth()
      redirectToLogin()
      return response
    }

    const retryHeaders = new Headers((init && init.headers) || {})
    retryHeaders.set('Authorization', 'Bearer ' + refreshedToken)
    response = await nativeFetch(input, { ...(init || {}), headers: retryHeaders })
    if (response.status === 401) {
      clearAuth()
      redirectToLogin()
    }
    return response
  }

  function requireAuthSession() {
    if (!getAccessToken() && !getRefreshToken()) {
      redirectToLogin()
      return false
    }
    return true
  }

  window.authFetch = authFetch
  window.requireAuthSession = requireAuthSession
})()
