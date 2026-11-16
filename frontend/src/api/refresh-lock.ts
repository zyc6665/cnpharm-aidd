/**
 * 跨标签页的刷新互斥。
 *
 * `request.ts` 里的 `isRefreshing` 是模块级变量：两个标签页各有一份模块实例，
 * 彼此看不见，于是同一次过期窗口内的两次刷新都会真的发到后端。这里把「谁去刷新」
 * 串行化——但只在浏览器真的提供了互斥原语时。
 *
 * 降级链只有两级（任一环节都不得抛错）：
 *   1. Web Locks —— 安全上下文且 `navigator.locks` 在场；
 *   2. 直接执行 —— 没有 Web Locks（非安全上下文 / 老浏览器 / jsdom），或
 *      `locks.request` **同步**抛错。
 *
 * 为什么第 2 级是「直接执行」，而不是原来那套 localStorage 租约（本文件曾实现过，
 * 现已整块删除）：
 *   - 无 Web Locks 时不互斥，落败方由后端 409/token_rotated 交棒，绝不二次轮换。
 *     409 的语义是「这张票 10 秒内刚被替换，不吊销、不清票据、不登出」，代价只是
 *     一次重放；而租约要同时管 TTL、续租、时钟漂移三件事，每一件都比 409 协议更
 *     容易出错——用一个更容易错的机制去避免一次已被协议兜住的失败，不划算。
 *   - 旧租约实际上也没换来互斥，反而多花 2s：
 *       TTL(5s) < REFRESH_TIMEOUT_MS(9s)，持锁者还在 IAM 校验里，租约就已过期；
 *       更关键的是 `acquireLease` 返回 null 之后代码照样执行 `task()`（fail-open
 *       写在代码里），于是第二个标签页在赢家 2.1s / 5.1s 后启动都会真的再发一次
 *       POST——白等 2s，一次刷新都没省下。
 *   所以这里不再假装互斥：拿不到锁就直接跑，把裁决权交给后端的 409。
 *
 * 任务的异步 reject 必须原样上抛，绝不兜底重跑：重跑会二次轮换 refresh，
 * 正好触发后端的复用检测（401 + 全端吊销）。
 */

/** 刷新用的锁名：同一来源（origin）下所有标签页共享。 */
export const AUTH_REFRESH_LOCK_NAME = 'auth:refresh'

type LockManagerLike = {
  request<T>(name: string, callback: () => Promise<T>): Promise<T>
}

/** 取 Web Locks 管理器；环境不支持时返回 null。 */
function getLockManager(): LockManagerLike | null {
  if (typeof navigator === 'undefined') {
    return null
  }

  const locks = (navigator as Navigator & { locks?: LockManagerLike }).locks
  if (!locks || typeof locks.request !== 'function') {
    return null
  }

  return locks
}

/**
 * 在 `auth:refresh` 锁内执行 `task`；没有 Web Locks 时直接执行（不互斥）。
 *
 * 只有 `locks.request(...)` 的**同步**调用才降级：任务自身的异步 reject 必须原样
 * 上抛，绝不能兜底再跑一次（会二次轮换 refresh，正好触发后端的复用检测）。
 * 抢不到锁时同样不做补偿：落败方的 409/token_rotated 由 `request.ts` 交棒。
 */
export async function withAuthRefreshLock<T>(task: () => Promise<T>): Promise<T> {
  const locks = getLockManager()
  if (!locks) {
    // 无 Web Locks 时不互斥，落败方由后端 409/token_rotated 交棒，绝不二次轮换。
    return task()
  }

  let pending: Promise<T>
  try {
    pending = locks.request(AUTH_REFRESH_LOCK_NAME, task)
  } catch {
    // 同步抛错（策略限制 / 旧实现）：等同「没有 Web Locks」，直接执行，且只执行一次。
    return task()
  }

  return pending
}
