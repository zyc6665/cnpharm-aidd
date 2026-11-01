/**
 * 浏览器 Cookie 读取工具。
 *
 * 认证改为后端下发的 httpOnly Cookie 后，前端只能读取非 httpOnly 的
 * `cpumodel_csrf`（用于 CSRF 头），其余 token 对 JS 不可见。
 */

export const CSRF_COOKIE_NAME = 'cpumodel_csrf'
export const CSRF_HEADER_NAME = 'X-CSRF-Token'

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

/** 读取指定名称的 Cookie，不存在时返回 null。 */
export function readCookie(name: string): string | null {
  if (typeof document === 'undefined' || typeof document.cookie !== 'string' || !document.cookie) {
    return null
  }

  const prefix = `${name}=`
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim()
    if (!trimmed.startsWith(prefix)) {
      continue
    }

    const rawValue = trimmed.slice(prefix.length)
    try {
      return decodeURIComponent(rawValue)
    } catch {
      return rawValue
    }
  }

  return null
}

/** 读取 CSRF Cookie（`cpumodel_csrf`）。 */
export function getCsrfToken(): string | null {
  return readCookie(CSRF_COOKIE_NAME)
}

/** 判断 HTTP 方法是否为无需 CSRF 校验的安全方法。 */
export function isSafeMethod(method?: string): boolean {
  return SAFE_METHODS.has((method || 'GET').toUpperCase())
}

/** 构造 CSRF 请求头：安全方法或无 CSRF Cookie 时返回空对象。 */
export function buildCsrfHeader(method?: string): Record<string, string> {
  const token = getCsrfToken()
  if (!token || isSafeMethod(method)) {
    return {}
  }

  return { [CSRF_HEADER_NAME]: token }
}
