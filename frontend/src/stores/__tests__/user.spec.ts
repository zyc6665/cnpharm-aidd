import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCurrentUser, ssoLogout as apiSsoLogout } from '@/api/auth'
import { clearTokens } from '@/api/request'
import { applySessionInvalid, consumeRefreshFailureReason } from '@/api/sso-session'
import { getCsrfToken } from '@/utils/cookies'
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

vi.mock('@/api/sso-session', () => ({
  applySessionInvalid: vi.fn(),
  consumeRefreshFailureReason: vi.fn(),
}))

vi.mock('@/utils/cookies', async importOriginal => {
  const actual = await importOriginal<typeof import('@/utils/cookies')>()
  return {
    ...actual,
    getCsrfToken: vi.fn(),
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

describe('user store session expiry', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(getCurrentUser).mockReset()
    vi.mocked(getCsrfToken).mockReset()
    vi.mocked(consumeRefreshFailureReason).mockReset()
    vi.mocked(applySessionInvalid).mockReset()
    vi.mocked(clearTokens).mockReset()
  })

  it('统一票据失效时只把原因交给决策点一次', async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new Error('401'))
    vi.mocked(consumeRefreshFailureReason).mockReturnValue('iam_session_expired')

    await useUserStore().fetchUserInfo()

    expect(applySessionInvalid).toHaveBeenCalledTimes(1)
    expect(applySessionInvalid).toHaveBeenCalledWith('iam_session_expired')
  })

  it('启动恢复会话失败同样走决策点', async () => {
    vi.mocked(getCsrfToken).mockReturnValue('csrf-token')
    vi.mocked(getCurrentUser).mockRejectedValue(new Error('401'))
    vi.mocked(consumeRefreshFailureReason).mockReturnValue('iam_session_expired')

    await useUserStore().bootstrapAuthState()

    expect(applySessionInvalid).toHaveBeenCalledTimes(1)
    expect(applySessionInvalid).toHaveBeenCalledWith('iam_session_expired')
  })

  it('没有原因（普通过期 / 网络错误）时不触发跳转决策', async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new Error('network down'))
    vi.mocked(consumeRefreshFailureReason).mockReturnValue(null)

    const store = useUserStore()
    store.userInfo = { id: 'u-3', username: 'wangwu' } as never
    await store.fetchUserInfo()

    expect(applySessionInvalid).not.toHaveBeenCalled()
    expect(store.userInfo).toBeNull()
  })
})
