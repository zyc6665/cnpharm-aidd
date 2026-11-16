import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import axios, { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'

const mocks = vi.hoisted(() => ({
  clearAuthStorage: vi.fn(),
  applySessionInvalid: vi.fn(),
  rememberRefreshFailure: vi.fn(),
}))

// 只替换「有副作用」的出口：request.ts 的判断逻辑（409 识别、handoff）仍用真实现。
vi.mock('@/utils/auth-storage', async importOriginal => {
  const actual = await importOriginal<typeof import('@/utils/auth-storage')>()
  return { ...actual, clearAuthStorage: mocks.clearAuthStorage }
})

vi.mock('./sso-session', async importOriginal => {
  const actual = await importOriginal<typeof import('./sso-session')>()
  return {
    ...actual,
    applySessionInvalid: mocks.applySessionInvalid,
    rememberRefreshFailure: mocks.rememberRefreshFailure,
  }
})

import { CSRF_COOKIE_NAME, getCsrfToken } from '@/utils/cookies'
import { AUTH_REFRESH_LOCK_NAME } from './refresh-lock'
import { REFRESH_TIMEOUT_MS, createRefreshCoordinator } from './refresh-coordinator'
import request, { get, REFRESH_HANDOFF_MAX_WAIT_MS } from './request'

const REFRESH_URL = '/api/v1/auth/refresh'

const setCsrf = (value: string): void => {
  document.cookie = `${CSRF_COOKIE_NAME}=${value}; path=/`
}

const clearCsrf = (): void => {
  document.cookie = `${CSRF_COOKIE_NAME}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
}

type FakeLocks = {
  request<T>(name: string, callback: () => Promise<T>): Promise<T>
}

function installLocks(locks: FakeLocks): void {
  Object.defineProperty(navigator, 'locks', { value: locks, configurable: true })
}

/** 队列化的假 LockManager：后到的请求等前一个回调结束再执行，锁名按调用顺序记录。 */
function installSerialLocks(names: string[]): void {
  let tail: Promise<unknown> = Promise.resolve()
  installLocks({
    request<T>(name: string, callback: () => Promise<T>): Promise<T> {
      names.push(name)
      const pending = tail.then(() => callback())
      tail = pending.catch(() => undefined)
      return pending
    },
  })
}

// —— 请求层夹具（把 401 / 409 / 5xx 直接做成 AxiosError，绕过真实网络） ——

const originalAdapter = request.defaults.adapter
let adapterCalls: InternalAxiosRequestConfig[] = []

const unauthorized = (config: InternalAxiosRequestConfig): AxiosError =>
  new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, {
    status: 401,
    statusText: 'Unauthorized',
    headers: {},
    config,
    data: { code: 40101, message: '未认证' },
  } as never)

const serverError = (config: InternalAxiosRequestConfig): AxiosError =>
  new AxiosError('Server Error', 'ERR_BAD_RESPONSE', config, undefined, {
    status: 500,
    statusText: 'Internal Server Error',
    headers: {},
    config,
    data: { code: 50000, message: '服务器内部错误' },
  } as never)

/** 后端并发落败：HTTP 409 + 业务码 40104 + detail.reason=token_rotated（不吊销、不清票据）。 */
const tokenRotatedConflict = (): AxiosError =>
  new AxiosError('Conflict', 'ERR_BAD_REQUEST', undefined, undefined, {
    status: 409,
    statusText: 'Conflict',
    headers: {},
    config: {} as InternalAxiosRequestConfig,
    data: {
      code: 40104,
      message: '会话正在其他窗口刷新，请稍后重试',
      data: null,
      detail: { reason: 'token_rotated' },
    },
  } as never)

const installAdapter = (
  handler: (config: InternalAxiosRequestConfig, call: number) => Promise<unknown>,
): void => {
  const adapter: AxiosAdapter = async config => {
    adapterCalls.push(config)
    const data = await handler(config, adapterCalls.length)
    return { data, status: 200, statusText: 'OK', headers: {}, config }
  }
  request.defaults.adapter = adapter
}

/**
 * 两个标签页共用一个后端的模型（跨标签页 Cookie 共享，但 POST /auth/refresh 是各自发的）：
 *   第 1 次 POST —— 赢家标签页，服务端轮换成功，但它的 Set-Cookie 还没落到本标签页；
 *   第 2 次 POST —— 本标签页（落败方），拿的是 10 秒内刚被替换的旧票 → 409。
 * 赢家的 Set-Cookie 在 300ms 后落地，模拟「跨标签页写 Cookie 有延迟」。
 * `cookieDelayMs` 可调大：用来验证 handoff 预算是否真的覆盖了赢家最慢的 IAM 路径。
 */
function installRaceRefreshPosts(cookieDelayMs = 300): { total: () => number } {
  let count = 0
  vi.spyOn(axios, 'post').mockImplementation(async () => {
    count += 1
    if (count === 1) {
      return { code: 0, message: 'ok', data: null }
    }
    window.setTimeout(() => setCsrf('csrf-new'), cookieDelayMs)
    throw tokenRotatedConflict()
  })
  return { total: () => count }
}

beforeEach(() => {
  vi.clearAllMocks()
  adapterCalls = []
  delete (navigator as { locks?: unknown }).locks
  setCsrf('csrf-old')
})

afterEach(() => {
  vi.restoreAllMocks()
  request.defaults.adapter = originalAdapter
  adapterCalls = []
  delete (navigator as { locks?: unknown }).locks
  clearCsrf()
})

describe('有 Web Locks：跨标签页真互斥', () => {
  it('赢家慢于 2s（旧租约预算）时落败方照样等着，总 POST 只有 1 次', async () => {
    const names: string[] = []
    installSerialLocks(names)

    // 赢家卡在 IAM 校验里：CSRF 在整个 gate 期间保持旧值，落败方没有任何「已刷新」的信号。
    let releaseWinner: () => void = () => undefined
    const winnerGate = new Promise<void>(resolve => {
      releaseWinner = resolve
    })
    const call = vi.fn(async () => {
      await winnerGate
      setCsrf('csrf-new')
    })

    const tabA = createRefreshCoordinator(call)
    const tabB = createRefreshCoordinator(call)

    const first = tabA.refresh('csrf-old')
    const second = tabB.refresh('csrf-old')

    // 2.1s：旧实现（租约 MAX_WAIT 2s / TTL 5s + 抢不到也照跑）会在这一刻放落败方过去。
    await new Promise<void>(resolve => window.setTimeout(resolve, 2_100))
    expect(call).toHaveBeenCalledTimes(1)

    releaseWinner()
    const outcomes = await Promise.all([first, second])

    expect(call).toHaveBeenCalledTimes(1)
    expect([...outcomes].sort()).toEqual(['handoff', 'refreshed'])
    expect(names).toEqual([AUTH_REFRESH_LOCK_NAME, AUTH_REFRESH_LOCK_NAME])
  })

  it('CSRF 已被另一标签页更新时直接交棒，不再刷新', async () => {
    const names: string[] = []
    installSerialLocks(names)
    setCsrf('csrf-new')

    const call = vi.fn(async () => undefined)
    const tab = createRefreshCoordinator(call)

    await expect(tab.refresh('csrf-old')).resolves.toBe('handoff')
    expect(call).toHaveBeenCalledTimes(0)
    expect(names).toEqual([AUTH_REFRESH_LOCK_NAME])
  })

  it('locks.request 同步抛错时直接执行，且只执行一次', async () => {
    installLocks({
      request() {
        throw new DOMException('x', 'SecurityError')
      },
    })
    const call = vi.fn(async () => undefined)
    const tab = createRefreshCoordinator(call)

    await expect(tab.refresh(null)).resolves.toBe('refreshed')
    expect(call).toHaveBeenCalledTimes(1)
  })

  it('任务的异步失败原样上抛，绝不兜底重跑（重跑会二次轮换 refresh）', async () => {
    installSerialLocks([])
    const failure = new Error('refresh failed')
    const call = vi.fn(async () => {
      throw failure
    })
    const tab = createRefreshCoordinator(call)

    await expect(tab.refresh(null)).rejects.toBe(failure)
    expect(call).toHaveBeenCalledTimes(1)
  })
})

describe('无 Web Locks：不假装互斥，由后端 409 仲裁', () => {
  it('两个标签页都会真的发 POST（fail-open），这正是 409 存在的理由', async () => {
    // jsdom 没有 navigator.locks；租约已删，所以这里没有任何东西能挡住第二个标签页。
    let releaseWinner: () => void = () => undefined
    const winnerGate = new Promise<void>(resolve => {
      releaseWinner = resolve
    })
    const call = vi.fn(async () => {
      await winnerGate
      setCsrf('csrf-new')
    })
    const tabA = createRefreshCoordinator(call)
    const tabB = createRefreshCoordinator(call)

    const first = tabA.refresh('csrf-old')
    const second = tabB.refresh('csrf-old')

    // 两个都进了 task：没人「等锁」，也就没人被租约的 2s 预算拖慢。
    expect(call).toHaveBeenCalledTimes(2)

    releaseWinner()
    await expect(Promise.all([first, second])).resolves.toEqual(['refreshed', 'refreshed'])
    expect(call).toHaveBeenCalledTimes(2)
  })

  it('落败方多发的那次 POST 拿到 409 后只重放一次：不清票据、不跳登录', async () => {
    // 赢家的 Set-Cookie 2.3s 后才落到本标签页，正好越过旧的 2s handoff 预算——这条用例
    // 因此同时钉住 F2：预算必须覆盖赢家最慢的 IAM 校验（SSO_TIMEOUT 5s），提前放弃就会
    // 拿旧 access 重放。重放能否成功由 Cookie 是否已换新决定：真实后端里旧 access 重放
    // 必然还是 401，request.ts 于是 clearTokens + applySessionInvalid，用户被误踢回登录页。
    const replayedWithFreshCookie: boolean[] = []
    installAdapter(async (config, call) => {
      if (call === 1) {
        // 请求发出时 CSRF 还是 csrf-old；赢家标签页在此期间完成轮换，本条此刻才拿到 401。
        await axios.post(REFRESH_URL)
        throw unauthorized(config)
      }
      const fresh = getCsrfToken() === 'csrf-new'
      replayedWithFreshCookie.push(fresh)
      if (!fresh) {
        throw unauthorized(config)
      }
      return { code: 0, message: 'ok', data: { ok: true } }
    })
    const refreshPosts = installRaceRefreshPosts(2_300)

    const response = await get<{ ok: true }>('/api/v1/projects')

    expect(response.data).toEqual({ ok: true })
    // 上限就是 2 次 POST：赢家 1 次 + 落败方 1 次；第 3 次就意味着仲裁被绕过了。
    expect(refreshPosts.total()).toBe(2)
    // 原始 401 + 恰好 1 次重放，且重放发生在赢家写完 Cookie 之后（2s 预算下会是 [false]）。
    expect(adapterCalls).toHaveLength(2)
    expect(replayedWithFreshCookie).toEqual([true])
    expect(mocks.clearAuthStorage).toHaveBeenCalledTimes(0)
    expect(mocks.applySessionInvalid).toHaveBeenCalledTimes(0)
  })

  it('重放真的 401 才算会话失效：清票据 + 走唯一决策点（对照组）', async () => {
    installAdapter(async (config, call) => {
      if (call === 1) {
        await axios.post(REFRESH_URL)
      }
      throw unauthorized(config)
    })
    const refreshPosts = installRaceRefreshPosts()

    await expect(get<unknown>('/api/v1/projects')).rejects.toBeTruthy()

    expect(refreshPosts.total()).toBe(2)
    expect(adapterCalls).toHaveLength(2)
    expect(mocks.clearAuthStorage).toHaveBeenCalledTimes(1)
    expect(mocks.applySessionInvalid).toHaveBeenCalledTimes(1)
    expect(mocks.applySessionInvalid).toHaveBeenCalledWith('token_rotated')
  })

  it('重放失败但不是 401（5xx）时不清票据（网络/服务端抖动 ≠ 会话失效）', async () => {
    installAdapter(async (config, call) => {
      if (call === 1) {
        await axios.post(REFRESH_URL)
        throw unauthorized(config)
      }
      throw serverError(config)
    })
    const refreshPosts = installRaceRefreshPosts()

    await expect(get<unknown>('/api/v1/projects')).rejects.toBeTruthy()

    expect(refreshPosts.total()).toBe(2)
    expect(mocks.clearAuthStorage).toHaveBeenCalledTimes(0)
    expect(mocks.applySessionInvalid).toHaveBeenCalledTimes(0)
  })
})

describe('预算不等式', () => {
  it('SSO_TIMEOUT <= handoff < 竞态窗口，且 REFRESH_TIMEOUT < 竞态窗口、handoff < REFRESH_TIMEOUT', () => {
    // 后端常量：backend/app/config.py:290 SSO_TIMEOUT_SECONDS = 5.0
    const SSO_TIMEOUT_MS = 5 * 1000
    // 后端常量：backend/app/services/refresh_token_store.py:28 ROTATE_RACE_WINDOW_SECONDS = 10
    const ROTATE_RACE_WINDOW_MS = 10 * 1000

    // 1) 落败方等新 Cookie 的预算必须覆盖赢家最慢的 IAM 路径，否则 2s 到点就重放旧 access → 误判登出。
    expect(REFRESH_HANDOFF_MAX_WAIT_MS).toBeGreaterThanOrEqual(SSO_TIMEOUT_MS)
    // 2) 但必须留在竞态窗口内：等过 10s，重放会被判成 refresh 复用（401 + 全端吊销）。
    expect(REFRESH_HANDOFF_MAX_WAIT_MS).toBeLessThan(ROTATE_RACE_WINDOW_MS)
    // 3) 刷新自身的超时也必须小于窗口，否则一次慢刷新直接跨进复用检测。
    expect(REFRESH_TIMEOUT_MS).toBeLessThan(ROTATE_RACE_WINDOW_MS)
    // 4) handoff 必须短于刷新超时：赢家已放弃时落败方不该还在等一张不会来的 Cookie。
    expect(REFRESH_HANDOFF_MAX_WAIT_MS).toBeLessThan(REFRESH_TIMEOUT_MS)
  })
})
