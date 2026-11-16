/**
 * 刷新协调器：把「谁来真正发 POST /auth/refresh」收敛成一次。
 *
 * 同页内的并发靠 `request.ts` 的 `isRefreshing` 排队；跨标签页靠
 * `withAuthRefreshLock`（只有 Web Locks 才真互斥：`refresh-lock.ts` 在没有它时
 * 不假装互斥，落败方由后端 409/token_rotated 交棒）。抢到锁之后先看 CSRF Cookie
 * 有没有被别的标签页换掉：换掉了说明别人刚刷完，本次直接交棒（`handoff`），让
 * 调用方拿新 Cookie 重放原请求，而不是用同一张旧 refresh 再轮换一次。
 */

import { getCsrfToken } from '@/utils/cookies'
import { withAuthRefreshLock } from './refresh-lock'

/** `refreshed`：本次真的刷新了；`handoff`：另一标签页已刷新，直接重放即可。 */
export type RefreshOutcome = 'refreshed' | 'handoff'

export type RefreshCall = () => Promise<void>

/**
 * 刷新请求超时：避免异常时把跨标签页的锁一直占住。
 *
 * 预算不等式（改任何一项前先读这几个数）：
 *   SSO_TIMEOUT_SECONDS * 1000 (5_000，backend/app/config.py:290)
 *     <= REFRESH_HANDOFF_MAX_WAIT_MS (6_000，request.ts)
 *     <  ROTATE_RACE_WINDOW_SECONDS * 1000 (10_000，backend/app/services/refresh_token_store.py:28)
 *   REFRESH_TIMEOUT_MS (9_000) < ROTATE_RACE_WINDOW_SECONDS * 1000 (10_000)
 *   REFRESH_HANDOFF_MAX_WAIT_MS (6_000) < REFRESH_TIMEOUT_MS (9_000)
 *
 * 上限必须 **小于** 后端竞态窗口：一次慢刷新若跨过 10s，后端就不再把它当「并发
 * 落败」，而是判成 refresh 复用（401 + 全端吊销）。原来的 15s 正好跨过了这条线。
 * 下限由 handoff 预算兜住：赢家最慢要花 SSO_TIMEOUT(5s) 等 IAM，落败方的 6s 交棒
 * 窗口必须短于赢家的 9s 上限，否则赢家已经放弃、落败方还在等一张不会来的新 Cookie。
 */
export const REFRESH_TIMEOUT_MS = 9_000

export function createRefreshCoordinator(call: RefreshCall) {
  let inFlight: Promise<RefreshOutcome> | null = null

  const run = (csrfAtFailure: string | null): Promise<RefreshOutcome> =>
    withAuthRefreshLock(async () => {
      const current = getCsrfToken()
      if (csrfAtFailure && current && current !== csrfAtFailure) {
        return 'handoff'
      }

      await call()
      return 'refreshed'
    })

  return {
    /**
     * 刷新一次。
     *
     * 并发调用共享同一个 Promise；结束后立刻清空，失败也不缓存（下一次重新发起，
     * 由调用方决定是否走失败路径）。
     */
    refresh(csrfAtFailure: string | null): Promise<RefreshOutcome> {
      if (!inFlight) {
        inFlight = run(csrfAtFailure).finally(() => {
          inFlight = null
        })
      }

      return inFlight
    },
  }
}
