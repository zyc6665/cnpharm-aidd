/**
 * 认证本地状态清理。
 *
 * JWT 已改由后端 httpOnly Cookie 承载，前端不再读写 access/refresh token。
 * 这里只保留历史遗留 token 的清理与「认证失效」广播，避免旧版本遗留在
 * localStorage 里的 token 继续生效。
 */

export const AUTH_CLEARED_EVENT = 'cpumodel-auth-cleared'

const LEGACY_TOKEN_KEY = 'cpumodel_token'
const LEGACY_REFRESH_TOKEN_KEY = 'cpumodel_refresh_token'

const removeStorageItem = (key: string): void => {
  if (typeof localStorage !== 'undefined') {
    localStorage.removeItem(key)
  }
}

/** 清除认证相关本地状态并广播事件，由用户 store 监听后清理内存用户信息。 */
export const clearAuthStorage = (): void => {
  removeStorageItem(LEGACY_TOKEN_KEY)
  removeStorageItem(LEGACY_REFRESH_TOKEN_KEY)

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AUTH_CLEARED_EVENT))
  }
}
