const PUBLIC_AUTH_PATHS = [
  '/auth/login',
  '/auth/logout',
  '/auth/refresh'
] as const

const API_PREFIX = '/api/v1'

const normalizeRequestPath = (url?: string): string => {
  if (!url) {
    return ''
  }

  try {
    const path = new URL(url, 'http://localhost').pathname
    return path.startsWith(API_PREFIX) ? path.slice(API_PREFIX.length) : path
  } catch {
    return url.startsWith(API_PREFIX) ? url.slice(API_PREFIX.length) : url
  }
}

const isPublicAuthPath = (url?: string): boolean => {
  const normalizedPath = normalizeRequestPath(url)

  return PUBLIC_AUTH_PATHS.some(path => (
    normalizedPath === path || normalizedPath.startsWith(`${path}/`)
  ))
}

/**
 * 是否允许在 401 后尝试通过 `POST /auth/refresh` 恢复会话。
 * 登录/刷新/登出接口自身失败时不再递归刷新。
 */
export const shouldAttemptTokenRefresh = (url?: string): boolean => {
  if (!url) {
    return true
  }

  return !isPublicAuthPath(url)
}
