import { redirectToLogin } from './auth-redirect'
import { readSsoStatusCache } from './sso-status'
import {
  IAM_SESSION_EXPIRED_REASON,
  buildSsoAuthorizeUrl,
  isLoginLocation,
  navigateToSso,
  resolveCurrentLocation
} from '@/utils/sso'

/**
 * 401 会话失效的**唯一决策点**：请求层与 store 都只把「原因」交给这里，
 * 由本模块决定是整页跳统一认证、回登录页，还是什么都不做。
 *
 * 之所以集中：刷新失败可能同时发生在拦截器和 store 的两个 catch 里，
 * 各自拼 URL 就一定会重复跳转、甚至互相覆盖。
 */

export interface SessionRuntime {
  pathname: string
  search: string
  /** 缓存里的统一认证开关；null 表示还没探测过 */
  ssoEnabled: boolean | null
  authorizePath: string | null
  apiBase: string
}

let ssoRedirectIssued = false
let pendingRefreshFailureReason: string | null = null

function currentRuntime(): SessionRuntime {
  const status = readSsoStatusCache().status
  return {
    pathname: typeof window !== 'undefined' ? window.location.pathname : '/',
    search: typeof window !== 'undefined' ? window.location.search : '',
    ssoEnabled: status ? Boolean(status.enabled) : null,
    authorizePath: status?.authorize_path ?? null,
    apiBase: import.meta.env.VITE_API_BASE_URL ?? ''
  }
}

/** 从 axios 401 里取出后端约定的 detail.reason；取不到返回 null */
export function readErrorReason(error: unknown): string | null {
  const response = (error as { response?: { data?: { detail?: unknown } } } | null)?.response
  const detail = response?.data?.detail ?? (error as { detail?: unknown } | null)?.detail
  if (typeof detail !== 'object' || detail === null) {
    return null
  }
  const reason = (detail as { reason?: unknown }).reason
  return typeof reason === 'string' && reason ? reason : null
}

/**
 * 刷新失败时记下原因：拦截器 reject 给调用方的是**原始 401**（没有 refresh 的
 * detail.reason），store 的 catch 只能靠这条旁路拿到「是不是统一票据失效」。
 */
export function rememberRefreshFailure(error: unknown): void {
  pendingRefreshFailureReason = readErrorReason(error)
}

export function consumeRefreshFailureReason(): string | null {
  const reason = pendingRefreshFailureReason
  pendingRefreshFailureReason = null
  return reason
}

/**
 * 决策表：
 * 1. 本生命周期已跳过一次 → none；
 * 2. 已经在登录页 → none（否则登录页自己 401 会无限跳）；
 * 3. 非 iam_session_expired，或统一认证明确未启用 → 回登录页（带 redirect）；
 * 4. 其余 → 顶层跳统一认证授权入口。
 */
export function applySessionInvalid(
  reason: string | null,
  overrides: Partial<SessionRuntime> = {}
): 'sso' | 'login' | 'none' {
  const runtime: SessionRuntime = { ...currentRuntime(), ...overrides }

  if (isLoginLocation(runtime.pathname)) {
    return 'none'
  }
  if (ssoRedirectIssued) {
    return 'none'
  }

  const location = resolveCurrentLocation(runtime.pathname, runtime.search)
  if (reason !== IAM_SESSION_EXPIRED_REASON || runtime.ssoEnabled === false) {
    redirectToLogin(location)
    return 'login'
  }

  // 先置位再跳：跳转是同步生效的，置位放后面会在 pagehide 前被重入
  ssoRedirectIssued = true
  navigateToSso(buildSsoAuthorizeUrl(runtime.authorizePath, location, runtime.apiBase))
  return 'sso'
}

/** 复位「只跳一次」标记与旁路原因：登出、测试、重新探测状态时调用 */
export function resetSsoSessionState(): void {
  ssoRedirectIssued = false
  pendingRefreshFailureReason = null
}
