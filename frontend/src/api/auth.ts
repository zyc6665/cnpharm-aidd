import { get, post, patch, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  UserInfo,
  LoginParams,
  LoginResponse,
  AuthTokens
} from '@/types/models'

// 用户登录（企业内网：账号 + 口令，后端按账号解析本地/LDAP 认证源）。
// 认证信息由后端通过 httpOnly Cookie 下发，响应里即使带 token 前端也忽略。
export const login = (params: LoginParams): Promise<ApiResponse<LoginResponse>> => {
  return post<LoginResponse>('/auth/login', params)
}

// 刷新会话：读取 refresh Cookie 并重设 Cookie，前端不接触 token。
export const refreshToken = (): Promise<ApiResponse<AuthTokens | { access_token?: string }>> => {
  return post<AuthTokens | { access_token?: string }>('/auth/refresh')
}

// 登出（后端清除 Cookie）
export const logout = (): Promise<ApiResponse<null>> => {
  return post<null>('/auth/logout')
}

// 获取当前用户信息（Cookie 会话有效即可返回，无需前端持有 token）
export const getCurrentUser = (config?: RequestOptions): Promise<ApiResponse<UserInfo>> => {
  return get<UserInfo>('/users/me', undefined, config)
}

// 更新当前用户信息
export const updateCurrentUser = (data: Partial<UserInfo>): Promise<ApiResponse<UserInfo>> => {
  return patch<UserInfo>('/users/me', data)
}
