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

export const shouldAttachAuthHeader = (url?: string): boolean => {
  if (!url) {
    return true
  }

  return !isPublicAuthPath(url)
}

export const shouldAttemptTokenRefresh = (url?: string): boolean => {
  if (!url) {
    return true
  }

  return !isPublicAuthPath(url)
}

export const buildRefreshTokenRequestConfig = (refreshToken: string) => ({
  params: {
    refresh_token: refreshToken
  }
})
