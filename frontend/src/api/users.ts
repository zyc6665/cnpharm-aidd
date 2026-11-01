import { get, post, patch, put, del } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  AdminUserListResponse,
  AdminUserStats,
  UserInfo
} from '@/types/models'

/**
 * 更新用户信息
 */
export interface UpdateUserProfileParams {
  email?: string
  phone?: string
  avatar_url?: string
  bio?: string
}

export const updateUserProfile = (data: UpdateUserProfileParams): Promise<ApiResponse<UserInfo>> => {
  return patch<UserInfo>('/users/me', data)
}

/**
 * 修改密码
 */
export interface ChangePasswordParams {
  old_password: string
  new_password: string
}

export const changePassword = (data: ChangePasswordParams): Promise<ApiResponse<{ message: string }>> => {
  return put<{ message: string }>('/users/me/password', data)
}

export interface AdminUserListParams {
  page?: number
  page_size?: number
  keyword?: string
  role?: string
  status?: string
}

export interface AdminUserUpdateParams {
  email?: string
  phone?: string
  role?: string
  status?: string
}

export interface AdminUserCreateParams {
  /** 账号名（必填），全局唯一 */
  username: string
  /** 邮箱可选；LDAP 用户可为空 */
  email?: string
  display_name?: string
  password?: string
  role?: string
  status?: string
  /** 认证来源：本地口令或企业 LDAP */
  auth_source: 'local' | 'ldap'
}

export interface AdminResetUserPasswordParams {
  new_password: string
}

export const adminGetUsers = (params?: AdminUserListParams): Promise<ApiResponse<AdminUserListResponse>> => {
  return get<AdminUserListResponse, AdminUserListParams>('/users/admin', params)
}

export const adminCreateUser = (data: AdminUserCreateParams): Promise<ApiResponse<UserInfo>> => {
  return post<UserInfo>('/users/admin', data)
}

export const adminGetUserStats = (): Promise<ApiResponse<AdminUserStats>> => {
  return get<AdminUserStats>('/users/admin/stats')
}

export const adminUpdateUser = (userId: string, data: AdminUserUpdateParams): Promise<ApiResponse<UserInfo>> => {
  return patch<UserInfo>(`/users/admin/${userId}`, data)
}

export const adminResetUserPassword = (
  userId: string,
  data: AdminResetUserPasswordParams
): Promise<ApiResponse<{ message: string }>> => {
  return post<{ message: string }>(`/users/admin/${userId}/reset-password`, data)
}

export const adminDeleteUser = (
  userId: string,
  hard?: boolean
): Promise<ApiResponse<{ message: string }>> => {
  return del<{ message: string }>(`/users/admin/${userId}`, {
    params: hard ? { hard: true } : undefined
  })
}
