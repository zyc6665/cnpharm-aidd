import { defineStore } from 'pinia'
import { ref, computed, onScopeDispose } from 'vue'
import type { UserInfo, LoginParams, RegisterParams } from '@/types/models'
import {
  changePassword as apiChangePassword,
  updateUserProfile
} from '@/api/users'
import { normalizeUserInfo } from '@/utils/user-normalization'
import {
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  getCurrentUser,
  guestLogin as apiGuestLogin,
  sendEmailCode as apiSendEmailCode,
  refreshToken as apiRefreshToken
} from '@/api/auth'
import {
  AUTH_CLEARED_EVENT,
  setToken,
  setRefreshToken,
  setGuestSession,
  clearTokens,
  getToken,
  getRefreshToken,
  getGuestSession
} from '@/api/request'

export const useUserStore = defineStore('user', () => {
  // State
  const token = ref<string | null>(getToken())
  const refreshToken = ref<string | null>(getRefreshToken())
  const guestSession = ref<string | null>(getGuestSession())
  const userInfo = ref<UserInfo | null>(null)
  const isGuest = ref(!!guestSession.value)
  const loading = ref(false)
  const authReady = ref(!getToken() && !getGuestSession())

  // Getters
  const isLoggedIn = computed(() => !!token.value && !isGuest.value)
  const isAuthenticated = computed(() => !!token.value || !!guestSession.value)
  const user = computed(() => normalizeUserInfo(userInfo.value))
  const isAdmin = computed(() => user.value?.role === 'admin')
  const username = computed(() => user.value?.username || (isGuest.value ? '游客' : ''))
  const userRole = computed(() => user.value?.role || (isGuest.value ? 'guest' : 'user'))
  const avatar = computed(() => user.value?.avatar || '')

  // Aliases for backwards compatibility
  const role = computed(() => userRole.value)

  const clearLocalAuthState = () => {
    token.value = null
    refreshToken.value = null
    guestSession.value = null
    userInfo.value = null
    isGuest.value = false
    authReady.value = true
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
      clearTokens()
      token.value = res.data.access_token
      refreshToken.value = res.data.refresh_token
      guestSession.value = null
      userInfo.value = normalizeUserInfo(res.data.user)
      isGuest.value = false
      setToken(res.data.access_token)
      setRefreshToken(res.data.refresh_token)
      return res.data
    } finally {
      loading.value = false
      authReady.value = true
    }
  }

  const bootstrapAuthState = async () => {
    if (!token.value || isGuest.value) {
      authReady.value = true
      return null
    }

    if (!userInfo.value) {
      return await fetchUserInfo()
    }

    authReady.value = true
    return userInfo.value
  }

  const register = async (params: RegisterParams) => {
    loading.value = true
    try {
      const res = await apiRegister(params)
      // 注册成功后自动登录
      if (res.data.access_token) {
        clearTokens()
        token.value = res.data.access_token
        refreshToken.value = res.data.refresh_token
        guestSession.value = null
        userInfo.value = normalizeUserInfo(res.data.user)
        isGuest.value = false
        setToken(res.data.access_token)
        setRefreshToken(res.data.refresh_token)
      }
      return res.data
    } finally {
      loading.value = false
      authReady.value = true
    }
  }

  // 游客模式登录
  const guestLogin = async () => {
    loading.value = true
    try {
      const res = await apiGuestLogin()
      clearTokens()
      token.value = null
      refreshToken.value = null
      guestSession.value = res.data.session_id
      isGuest.value = true
      userInfo.value = null
      setGuestSession(res.data.session_id)
      return res.data
    } finally {
      loading.value = false
      authReady.value = true
    }
  }

  // 发送邮箱验证码
  const sendEmailCode = async (email: string, purpose: 'register' | 'reset_password' = 'register') => {
    return await apiSendEmailCode(email, purpose)
  }

  const logout = async () => {
    try {
      if (!isGuest.value) {
        await apiLogout()
      }
    } catch {
      // 忽略退出登录的错误（如 401），因为无论如何都要清除本地数据
    } finally {
      clearLocalAuthState()
      clearTokens()
    }
  }

  const fetchUserInfo = async () => {
    if (!token.value || isGuest.value) return null
    loading.value = true
    try {
      const res = await getCurrentUser()
      userInfo.value = normalizeUserInfo(res.data)
      return res.data
    } catch {
      // Token 无效，清除状态
      clearLocalAuthState()
      clearTokens()
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

  // 刷新 Token
  const refreshAccessToken = async () => {
    if (!refreshToken.value) return false
    try {
      const res = await apiRefreshToken(refreshToken.value)
      token.value = res.data.access_token
      refreshToken.value = res.data.refresh_token
      setToken(res.data.access_token)
      setRefreshToken(res.data.refresh_token)
      authReady.value = true
      return true
    } catch {
      await logout()
      return false
    }
  }

  return {
    // State
    token,
    refreshToken,
    guestSession,
    userInfo,
    isGuest,
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
    register,
    guestLogin,
    sendEmailCode,
    logout,
    fetchUserInfo,
    bootstrapAuthState,
    updateUserInfo,
    refreshAccessToken,
    // Additional actions
    updateProfile,
    changePassword
  }
}, {
  persist: {
    pick: ['userInfo', 'isGuest']
  }
})
