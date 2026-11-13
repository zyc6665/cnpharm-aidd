/**
 * 统一身份认证（SSO）相关的纯函数：next 白名单、授权地址拼接、错误码映射、顶层跳转。
 *
 * 本模块**刻意零 import**：request.ts 会依赖它，若这里再依赖 api/* 就会形成循环。
 * 所有入参按 unknown 处理——值来自 URL / 接口，不可信，也绝不能抛异常打断登录页渲染。
 */

export const IAM_SESSION_EXPIRED_REASON = 'iam_session_expired'
export const LOGIN_PATH = '/login'
/** 后端未下发 authorize_path 时的兜底入口（与 auth_sso.AUTHORIZE_PATH 一致） */
export const SSO_AUTHORIZE_FALLBACK_PATH = '/api/v1/auth/sso/authorize'

/** 与后端 _safe_local_path 的 512 上限对齐，超长 next 一律丢弃 */
const NEXT_PATH_MAX_LENGTH = 512
const DEFAULT_NEXT_PATH = '/workspace'

const SSO_ERROR_CODES = [
  'disabled',
  'state',
  'denied',
  'token',
  'userinfo',
  'unavailable',
  'conflict',
  'inactive',
  'not_provisioned'
] as const

/** 取路径部分（去掉 query / hash），用于判断是不是登录页 */
function pathOnly(value: string): string {
  const cut = value.search(/[?#]/)
  const path = cut === -1 ? value : value.slice(0, cut)
  // 去掉尾部斜杠，让 /login 与 /login/ 等价；根路径保持 '/'
  return path.length > 1 ? path.replace(/\/+$/, '') || '/' : path
}

/**
 * 校验站内回跳地址，非法返回空串。
 *
 * 规则与后端 _safe_local_path 对齐（必须是 / 开头的站内路径、不含反斜杠与控制字符、
 * 不超过 512 字符），并额外拒绝登录页：统一认证回调若把 next 设成 /login，
 * 会话失效时就会在登录页与 IAM 之间来回跳。
 */
export function sanitizeNextPath(candidate: unknown): string {
  if (typeof candidate !== 'string' || candidate.length > NEXT_PATH_MAX_LENGTH) {
    return ''
  }
  if (/[\u0000-\u001f\u007f]/.test(candidate)) {
    return ''
  }
  const value = candidate.trim()
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return ''
  }
  if (isLoginLocation(value)) {
    return ''
  }
  return value
}

/** 回跳地址：合法则原样返回，否则落到工作台，保证 next 永远可用 */
export function resolveNextPath(candidate: unknown): string {
  return sanitizeNextPath(candidate) || DEFAULT_NEXT_PATH
}

/** 当前站内地址（pathname + search），用于 401 后带回原页面 */
export function resolveCurrentLocation(pathname: string, search = ''): string {
  const path = typeof pathname === 'string' && pathname ? pathname : '/'
  const query = typeof search === 'string' ? search : ''
  if (!query) {
    return path
  }
  return `${path}${query.startsWith('?') ? query : `?${query}`}`
}

/** 是否停在登录页（避免在登录页上再触发一次跳转） */
export function isLoginLocation(pathname: string): boolean {
  if (typeof pathname !== 'string' || !pathname) {
    return false
  }
  return pathOnly(pathname) === LOGIN_PATH
}

/**
 * 拼统一认证授权地址。
 *
 * 后端 authorize_path 已带 /api/v1 前缀，而 VITE_API_BASE_URL 通常也是 /api/v1：
 * 只有两者叠加成 `/api/v1/api/v1/...` 时才剥掉一层，正常路径原样保留，
 * 这样无论 apiBase 是空串、带不带尾斜杠，产出的地址都一致。
 */
export function buildSsoAuthorizeUrl(
  authorizePath: string | null | undefined,
  next: string,
  apiBase = ''
): string {
  const base = (typeof apiBase === 'string' ? apiBase : '').trim().replace(/\/+$/, '')
  let path = (typeof authorizePath === 'string' ? authorizePath.trim() : '') || SSO_AUTHORIZE_FALLBACK_PATH

  if (base && path.startsWith(`${base}${base}/`)) {
    path = path.slice(base.length)
  }
  if (base && !path.startsWith('/')) {
    path = `${base}/${path}`
  } else if (!path.startsWith('/')) {
    path = `/${path}`
  }

  const separator = path.includes('?') ? '&' : '?'
  return `${path}${separator}next=${encodeURIComponent(resolveNextPath(next))}`
}

/** 全仓唯一的 SSO 顶层跳转出口：换域名/换入口时只改这里 */
export function navigateToSso(url: string): void {
  window.location.assign(url)
}

/** ?sso_error=<码> → i18n 键；未知码与非字符串一律给通用文案 */
export function ssoErrorKey(value: unknown): string {
  if (typeof value !== 'string') {
    return 'auth.ssoError.unknown'
  }
  const code = value.trim()
  return (SSO_ERROR_CODES as readonly string[]).includes(code)
    ? `auth.ssoError.${code}`
    : 'auth.ssoError.unknown'
}
