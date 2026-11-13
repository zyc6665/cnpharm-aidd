import { defineStore } from 'pinia'
import { ref, computed, onScopeDispose } from 'vue'
import type { UserInfo, LoginParams } from '@/types/models'
import {
  changePassword as apiChangePassword,
  updateUserProfile
} from '@/api/users'
import { normalizeUserInfo } from '@/utils/user-normalization'
import {
  login as apiLogin,
  ssoLogout as apiSsoLogout,
  getCurrentUser
} from '@/api/auth'
import { AUTH_CLEARED_EVENT, clearTokens } from '@/api/request'
import { applySessionInvalid, consumeRefreshFailureReason } from '@/api/sso-session'
import { getCsrfToken } from '@/utils/cookies'

export const useUserStore = defineStore('user', () => {
  // State：不再持有 access/refresh token，登录态以 Cookie 会话 + userInfo 为准
  const userInfo = ref<UserInfo | null>(null)
  const loading = ref(false)
  const authReady = ref(false)
  let bootstrapPromise: Promise<UserInfo | null> | null = null

  // Getters
  const isLoggedIn = computed(() => !!userInfo.value)
  const isAuthenticated = isLoggedIn
  const user = computed(() => normalizeUserInfo(userInfo.value))
  const isAdmin = computed(() => user.value?.role === 'admin')
  const username = computed(() => user.value?.username || '')
  const userRole = computed(() => user.value?.role || 'user')
  const avatar = computed(() => user.value?.avatar || '')

  // Aliases for backwards compatibility
  const role = computed(() => userRole.value)

  const clearLocalAuthState = () => {
    userInfo.value = null
    authReady.value = true
  }

  /**
   * 会话失效后的跳转决策不在 store 里做：这里只把请求层旁路记下的「原因」
   * 交给 sso-session 这一个决策点，避免多个 catch 各拼一份 URL 重复跳转。
   */
  const applyPendingSessionInvalid = () => {
    const reason = consumeRefreshFailureReason()
    if (reason) {
      applySessionInvalid(reason)
    }
  }

  if (typeof window !== 'undefined') {
    window.addEventListener(AUTH_CLEARED_EVENT, clearLocalAuthState)
    onScopeDispose(() => {
      window.removeEventListener(AUTH_CLEARED_EVENT, clearLocalAuthState)
    })
  }

  // Actions
  const login = async (params: LoginParams) => {
    loading.value = true
    try {
      const res = await apiLogin(params)
      // 清理历史遗留 token，再写入用户信息
      clearTokens()
      userInfo.value = normalizeUserInfo(res.data.user)
      authReady.value = true
      return res.data
    } finally {
      loading.value = false
    }
  }

  /**
   * 启动时恢复会话：后端 Cookie 对 JS 不可见，因此用可读的 CSRF Cookie
   * 判断「可能已有会话」，再通过 GET /users/me 校验并恢复用户信息。
   * 没有 token 也能恢复；没有 CSRF Cookie 时直接视为未登录，避免公开页 401。
   */
  const bootstrapAuthState = async (force = false) => {
    if (!force && authReady.value) {
      return userInfo.value
    }

    if (bootstrapPromise) {
      return bootstrapPromise
    }

    bootstrapPromise = (async () => {
      if (!getCsrfToken()) {
        userInfo.value = null
        authReady.value = true
        return null
      }

      loading.value = true
      try {
        const res = await getCurrentUser({ silent: true, skipAuthRedirect: true })
        userInfo.value = normalizeUserInfo(res.data)
        return userInfo.value
      } catch {
        userInfo.value = null
        // 启动恢复走 skipAuthRedirect，跳不跳由决策点补做
        applyPendingSessionInvalid()
        return null
      } finally {
        loading.value = false
        authReady.value = true
      }
    })()

    try {
      return await bootstrapPromise
    } finally {
      bootstrapPromise = null
    }
  }

  /**
   * 退出登录：统一认证登出接口会吊销平台会话并返回甲方 GLO 地址。
   * 返回 null 表示没有 IAM 全局会话（local/ldap 用户、未启用 SSO 或接口失败），
   * 调用方据此决定回首页还是顶层跳转。无论接口成败都必须清本地状态。
   */
  const logout = async (): Promise<string | null> => {
    let logoutUrl: string | null = null
    try {
      const res = await apiSsoLogout()
      logoutUrl = res.data?.logout_url ?? null
    } catch {
      // 忽略退出登录的错误（如 401），因为无论如何都要清除本地数据
    } finally {
      clearTokens()
      clearLocalAuthState()
    }
    return logoutUrl
  }

  const fetchUserInfo = async () => {
    loading.value = true
    try {
      const res = await getCurrentUser()
      userInfo.value = normalizeUserInfo(res.data)
      return res.data
    } catch {
      // 会话无效，清除状态
      clearTokens()
      clearLocalAuthState()
      applyPendingSessionInvalid()
      return null
    } finally {
      loading.value = false
      authReady.value = true
    }
  }

  const updateUserInfo = (info: Partial<UserInfo>) => {
    if (userInfo.value) {
      userInfo.value = normalizeUserInfo({ ...userInfo.value, ...info })
    }
  }

  // 更新个人资料
  const updateProfile = async (data: { username?: string; avatar_url?: string }) => {
    const res = await updateUserProfile({
      avatar_url: data.avatar_url
    })
    userInfo.value = normalizeUserInfo({
      ...userInfo.value,
      ...res.data
    })
    return res.data
  }

  // 修改密码
  const changePassword = async (oldPassword: string, newPassword: string) => {
    await apiChangePassword({
      old_password: oldPassword,
      new_password: newPassword
    })
    return true
  }

  return {
    // State
    userInfo,
    loading,
    authReady,
    // Getters
    isLoggedIn,
    isAuthenticated,
    isAdmin,
    username,
    userRole,
    avatar,
    // Aliases
    user,
    role,
    // Actions
    login,
    logout,
    fetchUserInfo,
    bootstrapAuthState,
    updateUserInfo,
    // Additional actions
    updateProfile,
    changePassword
  }
}, {
  persist: {
    pick: ['userInfo']
  }
})
