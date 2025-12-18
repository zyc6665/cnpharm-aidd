import { get, post, put } from './request'
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

// 游客登录
export const guestLogin = (): Promise<ApiResponse<GuestLoginResponse>> => {
  return post<GuestLoginResponse>('/auth/guest')
}

// 发送邮箱验证码
export const sendEmailCode = (email: string): Promise<ApiResponse<{ message: string }>> => {
  return post<{ message: string }>('/auth/send-code', { email })
}

// 验证邮箱验证码
export const verifyEmailCode = (email: string, code: string): Promise<ApiResponse<{ valid: boolean }>> => {
  return post<{ valid: boolean }>('/auth/verify-code', { email, code })
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
  return get<UserInfo>('/auth/me')
}

// 更新当前用户信息
export const updateCurrentUser = (data: Partial<UserInfo>): Promise<ApiResponse<UserInfo>> => {
  return put<UserInfo>('/auth/me', data)
}

// 修改密码
export const changePassword = (oldPassword: string, newPassword: string): Promise<ApiResponse<null>> => {
  return post<null>('/auth/change-password', {
    old_password: oldPassword,
    new_password: newPassword
  })
}

// 忘记密码 - 发送重置邮件
export const forgotPassword = (email: string): Promise<ApiResponse<{ message: string }>> => {
  return post<{ message: string }>('/auth/forgot-password', { email })
}

// 重置密码
export const resetPassword = (token: string, newPassword: string): Promise<ApiResponse<null>> => {
  return post<null>('/auth/reset-password', {
    token,
    new_password: newPassword
  })
}

// 每日签到
export const dailySignIn = (): Promise<ApiResponse<{ reward: number; streak: number }>> => {
  return post<{ reward: number; streak: number }>('/auth/signin')
}

// 获取签到信息
export const getSignInInfo = (): Promise<ApiResponse<SignInInfo>> => {
  return get<SignInInfo>('/auth/signin/info')
}

// 验证邀请码
export const validateInvitationCode = (code: string): Promise<ApiResponse<{ valid: boolean; bonus?: number }>> => {
  return get<{ valid: boolean; bonus?: number }>(`/auth/invitation/${code}/validate`)
}
