import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import axios, { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'
import { message } from 'ant-design-vue'

const mocks = vi.hoisted(() => ({
  clearAuthStorage: vi.fn(),
  applySessionInvalid: vi.fn(),
  rememberRefreshFailure: vi.fn(),
}))

vi.mock('@/utils/auth-storage', async importOriginal => {
  const actual = await importOriginal<typeof import('@/utils/auth-storage')>()
  return { ...actual, clearAuthStorage: mocks.clearAuthStorage }
})

// 只替换两个「有副作用」的出口，``readErrorReason`` 仍用真实现（409 判定靠它）。
vi.mock('./sso-session', async importOriginal => {
  const actual = await importOriginal<typeof import('./sso-session')>()
  return {
    ...actual,
    applySessionInvalid: mocks.applySessionInvalid,
    rememberRefreshFailure: mocks.rememberRefreshFailure,
  }
})

import request, { get, REFRESH_HANDOFF_FIRST_DELAY_MS, REFRESH_HANDOFF_MAX_WAIT_MS } from './request'
import { REFRESH_TIMEOUT_MS } from './refresh-coordinator'

const originalAdapter = request.defaults.adapter
let adapterCalls: InternalAxiosRequestConfig[] = []

const setCsrf = (value: string): void => {
  document.cookie = `cpumodel_csrf=${value}; path=/`
}

const unauthorized = (config: InternalAxiosRequestConfig): AxiosError =>
  new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, {
    status: 401,
    statusText: 'Unauthorized',
    headers: {},
    config,
    data: { code: 40101, message: '未认证' },
  } as never)

/** 后端并发落败的响应：HTTP 409 + detail.reason=token_rotated。 */
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

const installAdapter = (handler: (config: InternalAxiosRequestConfig, call: number) => Promise<unknown>): void => {
  const adapter: AxiosAdapter = async config => {
    adapterCalls.push(config)
    const data = await handler(config, adapterCalls.length)
    return { data, status: 200, statusText: 'OK', headers: {}, config }
  }
  request.defaults.adapter = adapter
}

beforeEach(() => {
  vi.clearAllMocks()
  adapterCalls = []
  setCsrf('csrf-old')
})

afterEach(() => {
  vi.restoreAllMocks()
  request.defaults.adapter = originalAdapter
})

describe('并发刷新落败（409 / token_rotated）的重放', () => {
  it('不清 token、不跳转，Cookie 被成功方更新后重放一次', async () => {
    installAdapter(async (config, call) => {
      if (call === 1) {
        throw unauthorized(config)
      }
      return { code: 0, message: 'ok', data: { ok: true } }
    })
    const postSpy = vi.spyOn(axios, 'post').mockImplementation(async () => {
      // 另一个标签页刷成功了：Cookie 已被换掉，然后本标签页（晚到）才拿到 409。
      setCsrf('csrf-new')
      throw tokenRotatedConflict()
    })

    const response = await get<{ ok: boolean }>('/api/v1/projects')

    expect(response.data).toEqual({ ok: true })
    expect(adapterCalls).toHaveLength(2)
    expect(postSpy).toHaveBeenCalledTimes(1)
    expect(document.cookie).toContain('cpumodel_csrf=csrf-new')
    // 并发落败不是入侵：不许清本地态、不许跳 IAM/登录页。
    expect(mocks.clearAuthStorage).toHaveBeenCalledTimes(0)
    expect(mocks.applySessionInvalid).toHaveBeenCalledTimes(0)
  })

  it('重放仍失败时才走既有失败路径（只重放一次、不重复 toast）', async () => {
    installAdapter(async config => {
      throw unauthorized(config)
    })
    const postSpy = vi.spyOn(axios, 'post').mockImplementation(async () => {
      setCsrf('csrf-new')
      throw tokenRotatedConflict()
    })
    const errorToast = vi.spyOn(message, 'error').mockImplementation(() => undefined as never)

    await expect(get<unknown>('/api/v1/projects')).rejects.toBeTruthy()

    expect(adapterCalls).toHaveLength(2)
    expect(postSpy).toHaveBeenCalledTimes(1)
    expect(mocks.clearAuthStorage).toHaveBeenCalledTimes(1)
    expect(mocks.applySessionInvalid).toHaveBeenCalledTimes(1)
    expect(mocks.applySessionInvalid).toHaveBeenCalledWith('token_rotated')
    // 重放带 silent: true：失败时不再弹一次 toast。
    expect(errorToast).toHaveBeenCalledTimes(0)
  })
})

describe('跨标签页等待预算', () => {
  it('等待上限落在 [SSO_TIMEOUT, 竞态窗口) 之间，且短于刷新超时', () => {
    // 后端常量：backend/app/config.py:290 SSO_TIMEOUT_SECONDS = 5.0
    const SSO_TIMEOUT_MS = 5 * 1000
    // 后端常量：backend/app/services/refresh_token_store.py:28 ROTATE_RACE_WINDOW_SECONDS = 10
    const ROTATE_RACE_WINDOW_MS = 10 * 1000

    expect(REFRESH_HANDOFF_FIRST_DELAY_MS).toBeLessThan(REFRESH_HANDOFF_MAX_WAIT_MS)
    // 曾经钉成 2_000：小于赢家最慢的 IAM 校验（5s），到点重放旧 access 会被误判成登出。
    // 现在从 request.ts 导出的常量取值，只断言不等式，不再复制一份数字。
    expect(REFRESH_HANDOFF_MAX_WAIT_MS).toBeGreaterThanOrEqual(SSO_TIMEOUT_MS)
    expect(REFRESH_HANDOFF_MAX_WAIT_MS).toBeLessThan(ROTATE_RACE_WINDOW_MS)
    expect(REFRESH_HANDOFF_MAX_WAIT_MS).toBeLessThan(REFRESH_TIMEOUT_MS)
  })
})
