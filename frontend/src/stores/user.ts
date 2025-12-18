import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserInfo, LoginParams, RegisterParams, SignInInfo } from '@/types/models'
import {
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  getCurrentUser,
  guestLogin as apiGuestLogin,
  sendEmailCode as apiSendEmailCode,
  dailySignIn as apiDailySignIn,
  getSignInInfo as apiGetSignInInfo
} from '@/api/auth'
import { setToken, setRefreshToken, clearTokens, getToken } from '@/api/request'

export const useUserStore = defineStore('user', () => {
  // State
  const token = ref<string | null>(getToken())
  const refreshToken = ref<string | null>(null)
  const userInfo = ref<UserInfo | null>(null)
  const credits = ref(0)
  const isGuest = ref(false)
  const loading = ref(false)
  const signInInfo = ref<SignInInfo | null>(null)

  // Getters
  const isLoggedIn = computed(() => !!token.value && !isGuest.value)
  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => userInfo.value?.role === 'admin')
  const isVip = computed(() => userInfo.value?.role === 'vip' || userInfo.value?.role === 'admin')
  const username = computed(() => userInfo.value?.username || (isGuest.value ? '游客' : ''))
  const userRole = computed(() => userInfo.value?.role || (isGuest.value ? 'guest' : 'user'))
  const hasEnoughCredits = computed(() => (required: number) => credits.value >= required)
  const memberExpireAt = computed(() => userInfo.value?.member_expire_at)
  const invitationCode = computed(() => userInfo.value?.invitation_code)

  // Aliases for backwards compatibility
  const user = computed(() => userInfo.value)
  const role = computed(() => userRole.value)

  // Actions
  const login = async (params: LoginParams) => {
    loading.value = true
    try {
      const res = await apiLogin(params)
      token.value = res.data.access_token
      refreshToken.value = res.data.refresh_token
      userInfo.value = res.data.user
      credits.value = res.data.credits || res.data.user.credits || 0
      isGuest.value = false
      setToken(res.data.access_token)
      setRefreshToken(res.data.refresh_token)
      return res.data
    } finally {
      loading.value = false
    }
  }

  const register = async (params: RegisterParams) => {
    loading.value = true
    try {
      const res = await apiRegister(params)
      // 注册成功后自动登录
      if (res.data.access_token) {
        token.value = res.data.access_token
        refreshToken.value = res.data.refresh_token
        userInfo.value = res.data.user
        credits.value = res.data.credits || 100 // 注册奖励积分
        isGuest.value = false
        setToken(res.data.access_token)
        setRefreshToken(res.data.refresh_token)
      }
      return res.data
    } finally {
      loading.value = false
    }
  }

  // 游客模式登录
  const guestLogin = async () => {
    loading.value = true
    try {
      const res = await apiGuestLogin()
      token.value = res.data.access_token
      isGuest.value = true
      credits.value = 0
      userInfo.value = null
      setToken(res.data.access_token)
      return res.data
    } finally {
      loading.value = false
    }
  }

  // 发送邮箱验证码
  const sendEmailCode = async (email: string) => {
    return await apiSendEmailCode(email)
  }

  const logout = async () => {
    try {
      if (!isGuest.value) {
        await apiLogout()
      }
    } finally {
      token.value = null
      refreshToken.value = null
      userInfo.value = null
      credits.value = 0
      isGuest.value = false
      signInInfo.value = null
      clearTokens()
    }
  }

  const fetchUserInfo = async () => {
    if (!token.value || isGuest.value) return null
    loading.value = true
    try {
      const res = await getCurrentUser()
      userInfo.value = res.data
      credits.value = res.data.credits || 0
      return res.data
    } catch {
      // Token 无效，清除状态
      token.value = null
      refreshToken.value = null
      userInfo.value = null
      credits.value = 0
      isGuest.value = false
      clearTokens()
      return null
    } finally {
      loading.value = false
    }
  }

  // 获取积分（刷新）
  const fetchCredits = async () => {
    if (!token.value || isGuest.value) return
    const res = await getCurrentUser()
    credits.value = res.data.credits || 0
  }

  // 消费积分（本地更新）
  const consumeCredits = (amount: number) => {
    credits.value -= amount
  }

  // 增加积分（本地更新）
  const addCredits = (amount: number) => {
    credits.value += amount
  }

  // 每日签到
  const dailySignIn = async () => {
    if (isGuest.value) {
      throw new Error('游客模式不支持签到')
    }
    const res = await apiDailySignIn()
    if (res.data.reward) {
      credits.value += res.data.reward
    }
    await fetchSignInInfo()
    return res.data
  }

  // 获取签到信息
  const fetchSignInInfo = async () => {
    if (isGuest.value) return null
    try {
      const res = await apiGetSignInInfo()
      signInInfo.value = res.data
      return res.data
    } catch {
      return null
    }
  }

  const updateUserInfo = (info: Partial<UserInfo>) => {
    if (userInfo.value) {
      userInfo.value = { ...userInfo.value, ...info }
    }
  }

  // 更新个人资料
  const updateProfile = async (data: { username?: string; avatar?: string }) => {
    // TODO: 实现 API 调用
    if (userInfo.value) {
      userInfo.value = { ...userInfo.value, ...data }
    }
  }

  // 修改密码
  const changePassword = async (_oldPassword: string, _newPassword: string) => {
    // TODO: 实现 API 调用
    // 模拟成功
    return true
  }

  // 刷新 Token
  const refreshAccessToken = async () => {
    if (!refreshToken.value) return false
    try {
      const { refreshToken: apiRefreshToken } = await import('@/api/auth')
      const res = await apiRefreshToken(refreshToken.value)
      token.value = res.data.access_token
      refreshToken.value = res.data.refresh_token
      setToken(res.data.access_token)
      setRefreshToken(res.data.refresh_token)
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
    userInfo,
    credits,
    isGuest,
    loading,
    signInInfo,
    // Getters
    isLoggedIn,
    isAuthenticated,
    isAdmin,
    isVip,
    username,
    userRole,
    hasEnoughCredits,
    memberExpireAt,
    invitationCode,
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
    fetchCredits,
    consumeCredits,
    addCredits,
    dailySignIn,
    fetchSignInInfo,
    updateUserInfo,
    refreshAccessToken,
    // Additional actions
    updateProfile,
    changePassword
  }
}, {
  persist: {
    pick: ['token', 'refreshToken', 'isGuest', 'credits']
  }
})
