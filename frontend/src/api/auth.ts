import { get, post, patch } from './request'
import type { ApiResponse } from '@/types/api'
import { buildRefreshTokenRequestConfig } from './auth-request-policy'
import type {
  UserInfo,
  LoginParams,
  RegisterParams,
  LoginResponse,
  AuthTokens
} from '@/types/models'

// 用户登录
export const login = (params: LoginParams): Promise<ApiResponse<LoginResponse>> => {
  return post<LoginResponse>('/auth/login', params)
}

// 用户注册
export const register = (params: RegisterParams): Promise<ApiResponse<LoginResponse>> => {
  return post<LoginResponse>('/auth/register', params)
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
  return post<AuthTokens>('/auth/refresh', undefined, buildRefreshTokenRequestConfig(refresh_token))
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
