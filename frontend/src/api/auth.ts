import { get, post, patch, type RequestOptions } from './request'
import {
  isSsoStatusCacheFresh,
  readSsoStatusCache,
  writeSsoStatusCache
} from './sso-status'
import type { ApiResponse } from '@/types/api'
import type {
  UserInfo,
  LoginParams,
  LoginResponse,
  AuthTokens,
  SsoStatus
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

// 统一认证登出：后端吊销平台会话并返回甲方 GLO 地址，前端需顶层跳转
// （axios 跟随跨域 302 时 JS 读不到最终地址，IAM 的 Cookie 也不会被清）。
// logout_url 为 null 表示没有 IAM 全局会话（local/ldap 用户或未启用 SSO）。
export const ssoLogout = (): Promise<ApiResponse<{ logout_url: string | null }>> => {
  return post<{ logout_url: string | null }>('/auth/sso/logout')
}

// 获取当前用户信息（Cookie 会话有效即可返回，无需前端持有 token）
export const getCurrentUser = (config?: RequestOptions): Promise<ApiResponse<UserInfo>> => {
  return get<UserInfo>('/users/me', undefined, config)
}

// 更新当前用户信息
export const updateCurrentUser = (data: Partial<UserInfo>): Promise<ApiResponse<UserInfo>> => {
  return patch<UserInfo>('/users/me', data)
}

// 统一认证是否启用：登录页入口与 401 决策共用，60 秒缓存。
// 失败不缓存、不抛错、也不弹全局错误——认证服务异常时本地账号登录必须照常可用，
// 所以只返回上一次的值或 null，由调用方按「未启用」处理。
export const getSsoStatus = async (options?: { force?: boolean }): Promise<SsoStatus | null> => {
  if (!options?.force && isSsoStatusCacheFresh()) {
    return readSsoStatusCache().status
  }
  try {
    const response = await get<SsoStatus>('/auth/sso/status', undefined, {
      silent: true,
      skipAuthRedirect: true
    })
    const status = response?.data ?? null
    if (status && typeof status === 'object') {
      writeSsoStatusCache(status)
      return status
    }
    return readSsoStatusCache().status
  } catch {
    return readSsoStatusCache().status
  }
}

