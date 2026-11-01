import type { AdminUserCreateParams } from '@/api/users'

export interface AdminUserCreateForm {
  username: string
  email?: string | null
  display_name?: string
  password?: string
  role?: string
  status?: string
  auth_source: 'local' | 'ldap'
}

/**
 * 构造管理员创建用户的请求体。
 * - username 必填，去除首尾空白；
 * - email 为空时不下发（LDAP 用户可不填）；
 * - LDAP 用户不下发口令，由目录服务管理。
 */
export function buildAdminUserCreatePayload(form: AdminUserCreateForm): AdminUserCreateParams {
  const payload: AdminUserCreateParams = {
    username: form.username.trim(),
    display_name: form.display_name || undefined,
    role: form.role,
    status: form.status,
    auth_source: form.auth_source
  }
  const email = form.email?.trim()
  if (email) {
    payload.email = email
  }
  if (form.auth_source === 'local' && form.password) {
    payload.password = form.password
  }
  return payload
}
