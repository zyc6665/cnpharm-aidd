import type { SsoStatus } from '@/types/models'

/**
 * 统一认证启用状态的进程内缓存。
 *
 * 只允许 `import type`：本文件是叶子模块，request.ts → sso-session → 这里，
 * 若再引 api/* 就会和 request.ts 成环。缓存的目的不是提速，而是让
 * 「登录页读状态」与「401 决策」共用同一次探测结果，避免每 401 都打一次 /status。
 */

export const SSO_STATUS_TTL_MS = 60_000

interface SsoStatusCache {
  status: SsoStatus | null
  fetchedAt: number
}

let cache: SsoStatusCache = { status: null, fetchedAt: 0 }

export function readSsoStatusCache(): SsoStatusCache {
  return cache
}

export function isSsoStatusCacheFresh(now = Date.now()): boolean {
  return cache.status !== null && now - cache.fetchedAt < SSO_STATUS_TTL_MS
}

export function writeSsoStatusCache(status: SsoStatus, now = Date.now()): void {
  cache = { status, fetchedAt: now }
}

/** 复位缓存：登出、测试与「状态可能刚被管理员改过」的强制刷新场景用 */
export function resetSsoStatusCache(): void {
  cache = { status: null, fetchedAt: 0 }
}
