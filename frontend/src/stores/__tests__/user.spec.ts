import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ssoLogout as apiSsoLogout } from '@/api/auth'
import { clearTokens } from '@/api/request'
import { useUserStore } from '../user'

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  ssoLogout: vi.fn(),
  logout: vi.fn(),
  getCurrentUser: vi.fn(),
}))

vi.mock('@/api/users', () => ({
  changePassword: vi.fn(),
  updateUserProfile: vi.fn(),
}))

vi.mock('@/api/request', async importOriginal => {
  const actual = await importOriginal<typeof import('@/api/request')>()
  return {
    ...actual,
    clearTokens: vi.fn(),
  }
})

describe('user store logout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(apiSsoLogout).mockReset()
    vi.mocked(clearTokens).mockReset()
  })

  it('returns the IAM logout url and clears local auth state', async () => {
    vi.mocked(apiSsoLogout).mockResolvedValue({
      code: 200,
      message: '登出成功',
      data: { logout_url: 'https://iam.example/auth/api/user/webungateway/GLO?appId=x' },
    } as never)

    const store = useUserStore()
    store.userInfo = { id: 'u-1', username: 'zhangsan' } as never

    const url = await store.logout()

    expect(apiSsoLogout).toHaveBeenCalledTimes(1)
    expect(url).toBe('https://iam.example/auth/api/user/webungateway/GLO?appId=x')
    expect(clearTokens).toHaveBeenCalledTimes(1)
    expect(store.userInfo).toBeNull()
    expect(store.isLoggedIn).toBe(false)
  })

  it('returns null when there is no IAM global session', async () => {
    vi.mocked(apiSsoLogout).mockResolvedValue({
      code: 200,
      message: '登出成功',
      data: { logout_url: null },
    } as never)

    const url = await useUserStore().logout()

    expect(url).toBeNull()
    expect(clearTokens).toHaveBeenCalledTimes(1)
  })

  it('still clears local state and returns null when the request fails', async () => {
    vi.mocked(apiSsoLogout).mockRejectedValue(new Error('network down'))

    const store = useUserStore()
    store.userInfo = { id: 'u-2', username: 'lisi' } as never

    const url = await store.logout()

    expect(url).toBeNull()
    expect(clearTokens).toHaveBeenCalledTimes(1)
    expect(store.userInfo).toBeNull()
  })
})
