import { create } from 'zustand'
import {
  type AuthUser,
  clearStoredAuth,
  getStoredAccessToken,
  getStoredRefreshToken,
  getStoredUser,
  persistAuth,
  updateStoredAccessToken,
} from '../lib/auth'

type LoginInput = {
  username: string
  password: string
}

type RegisterInput = {
  username: string
  email?: string
  password: string
  invite_code?: string
}

type AuthState = {
  accessToken: string | null
  refreshToken: string | null
  user: AuthUser | null
  initialized: boolean
  hydrate: () => void
  setAccessToken: (accessToken: string | null) => void
  setSession: (accessToken: string, refreshToken: string, user: AuthUser) => void
  clearSession: () => void
  fetchMe: () => Promise<AuthUser>
  login: (input: LoginInput) => Promise<AuthUser>
  register: (input: RegisterInput) => Promise<AuthUser>
  logout: () => Promise<void>
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  let data: any = {}
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = {}
    }
  }
  if (!response.ok) {
    const detail =
      typeof data?.detail === 'string'
        ? data.detail
        : typeof data?.message === 'string'
          ? data.message
          : text && !text.trim().startsWith('<')
            ? text.trim()
            : `请求失败（HTTP ${response.status}）。`
    throw new Error(detail)
  }
  return data as T
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  refreshToken: null,
  user: null,
  initialized: false,

  hydrate: () => {
    set({
      accessToken: getStoredAccessToken(),
      refreshToken: getStoredRefreshToken(),
      user: getStoredUser(),
      initialized: true,
    })
  },

  setAccessToken: (accessToken) => {
    if (accessToken) {
      updateStoredAccessToken(accessToken)
    } else {
      clearStoredAuth()
    }
    set({ accessToken })
  },

  setSession: (accessToken, refreshToken, user) => {
    persistAuth(accessToken, refreshToken, user)
    set({ accessToken, refreshToken, user, initialized: true })
  },

  clearSession: () => {
    clearStoredAuth()
    set({ accessToken: null, refreshToken: null, user: null, initialized: true })
  },

  fetchMe: async () => {
    const accessToken = get().accessToken
    if (!accessToken) {
      throw new Error('未登录。')
    }
    const response = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    const user = await parseJson<AuthUser>(response)
    persistAuth(accessToken, get().refreshToken || '', user)
    set({ user })
    return user
  },

  login: async ({ username, password }) => {
    const formData = new URLSearchParams()
    formData.set('username', username)
    formData.set('password', password)

    const loginResponse = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData.toString(),
    })
    const tokens = await parseJson<{
      access_token: string
      refresh_token: string
      token_type: string
    }>(loginResponse)

    const meResponse = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    })
    const user = await parseJson<AuthUser>(meResponse)
    get().setSession(tokens.access_token, tokens.refresh_token, user)
    return user
  },

  register: async (input) => {
    const registerResponse = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
    await parseJson(registerResponse)
    try {
      return await get().login({ username: input.username, password: input.password })
    } catch (error: any) {
      throw new Error(error?.message || '注册成功，但自动登录失败，请返回登录页重试。')
    }
  },

  logout: async () => {
    const accessToken = get().accessToken
    if (accessToken) {
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: { Authorization: `Bearer ${accessToken}` },
        })
      } catch {
        // Ignore network/logout errors and clear local session anyway.
      }
    }
    get().clearSession()
  },
}))
