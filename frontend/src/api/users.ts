import { patch, put } from './request'
import type { ApiResponse } from '@/types/api'
import type { UserInfo } from '@/types/models'

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
