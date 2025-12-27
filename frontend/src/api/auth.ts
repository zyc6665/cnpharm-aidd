import { get, post, put, patch } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  UserInfo,
  LoginParams,
  RegisterParams,
  LoginResponse,
  AuthTokens,
  GuestLoginResponse,
  SignInInfo
} from '@/types/models'

// 用户登录
export const login = (params: LoginParams): Promise<ApiResponse<LoginResponse>> => {
  return post<LoginResponse>('/auth/login', params)
}

// 用户注册
export const register = (params: RegisterParams): Promise<ApiResponse<LoginResponse>> => {
  return post<LoginResponse>('/auth/register', params)
}

// 游客登录（临时实现，返回模拟数据）
export const guestLogin = (): Promise<ApiResponse<GuestLoginResponse>> => {
  // TODO: 后端实现后替换为真实API调用
  return Promise.resolve({
    code: 200,
    message: 'success',
    data: {
      access_token: 'guest_token_' + Date.now(),
      token_type: 'Bearer',
      expires_in: 3600
    }
  })
}

// 发送邮箱验证码
export const sendEmailCode = (
  email: string,
  purpose: 'register' | 'reset_password'
): Promise<ApiResponse<{ expires_in: number }>> => {
  return post<{ expires_in: number }>('/verification/send-code', { email, purpose })
}

// 验证邮箱验证码
export const verifyEmailCode = (
  email: string,
  code: string,
  purpose: 'register' | 'reset_password'
): Promise<ApiResponse<{ valid: boolean }>> => {
  return post<{ valid: boolean }>('/verification/verify', { email, code, purpose })
}

// 刷新 Token
export const refreshToken = (refresh_token: string): Promise<ApiResponse<AuthTokens>> => {
  return post<AuthTokens>('/auth/refresh', { refresh_token })
}

// 登出
export const logout = (): Promise<ApiResponse<null>> => {
  return post<null>('/auth/logout')
}

// 获取当前用户信息
export const getCurrentUser = (): Promise<ApiResponse<UserInfo>> => {
  return get<UserInfo>('/users/me')
}

// 更新当前用户信息
export const updateCurrentUser = (data: Partial<UserInfo>): Promise<ApiResponse<UserInfo>> => {
  return patch<UserInfo>('/users/me', data)
}

// 修改密码
export const changePassword = (oldPassword: string, newPassword: string): Promise<ApiResponse<null>> => {
  return put<null>('/users/me/password', {
    old_password: oldPassword,
    new_password: newPassword
  })
}

// 忘记密码 - 发送重置邮件（已废弃，使用 sendEmailCode 替代）
// export const forgotPassword = (email: string): Promise<ApiResponse<{ message: string }>> => {
//   return post<{ message: string }>('/auth/forgot-password', { email })
// }

// 重置密码（忘记密码场景）
export const resetPassword = (
  email: string,
  code: string,
  newPassword: string
): Promise<ApiResponse<null>> => {
  return post<null>('/auth/reset-password', {
    email,
    code,
    new_password: newPassword
  })
}

// 每日签到（临时实现，返回模拟数据）
export const dailySignIn = (): Promise<ApiResponse<{ reward: number; streak: number }>> => {
  // TODO: 后端实现后替换为真实API调用
  return Promise.resolve({
    code: 200,
    message: 'success',
    data: {
      reward: 10,
      streak: 1
    }
  })
}

// 获取签到信息（临时实现，返回模拟数据）
export const getSignInInfo = (): Promise<ApiResponse<SignInInfo>> => {
  // TODO: 后端实现后替换为真实API调用
  return Promise.resolve({
    code: 200,
    message: 'success',
    data: {
      signed_days: 0,
      already_signed: false,
      today_reward: 10,
      streak_bonus: false
    }
  })
}

// 验证邀请码（临时实现，返回模拟数据）
export const validateInvitationCode = (code: string): Promise<ApiResponse<{ valid: boolean; bonus?: number }>> => {
  // TODO: 后端实现后替换为真实API调用
  return Promise.resolve({
    code: 200,
    message: 'success',
    data: {
      valid: code.length === 6,
      bonus: code.length === 6 ? 50 : undefined
    }
  })
}
