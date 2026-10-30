import { get, post, patch } from './request'
import type { ApiResponse } from '@/types/api'
import { buildRefreshTokenRequestConfig } from './auth-request-policy'
import type {
  UserInfo,
  LoginParams,
  LoginResponse,
  AuthTokens
} from '@/types/models'

// 用户登录（企业内网：账号 + 口令，后端按账号解析本地/LDAP 认证源）
export const login = (params: LoginParams): Promise<ApiResponse<LoginResponse>> => {
  return post<LoginResponse>('/auth/login', params)
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
