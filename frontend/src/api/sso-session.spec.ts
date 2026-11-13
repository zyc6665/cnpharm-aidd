import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  navigateToSso: vi.fn(),
  redirectToLogin: vi.fn()
}))

vi.mock('@/utils/sso', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/utils/sso')>()
  return { ...actual, navigateToSso: mocks.navigateToSso }
})

vi.mock('@/api/auth-redirect', () => ({ redirectToLogin: mocks.redirectToLogin }))

import { resetSsoStatusCache, writeSsoStatusCache } from '@/api/sso-status'
import {
  applySessionInvalid,
  consumeRefreshFailureReason,
  readErrorReason,
  rememberRefreshFailure,
  resetSsoSessionState
} from '@/api/sso-session'

const TASKS_RUNTIME = { pathname: '/tasks', search: '?page=2', apiBase: '' }

function iamExpiredError() {
  return {
    response: {
      status: 401,
      data: { detail: { reason: 'iam_session_expired' } }
    }
  }
}

describe('readErrorReason', () => {
  it('取出 axios 401 body.detail.reason', () => {
    expect(readErrorReason(iamExpiredError())).toBe('iam_session_expired')
  })

  it('detail 是字符串 / 缺失 / 非对象时不抛错也不误判', () => {
    expect(readErrorReason({ response: { data: { detail: 'Unauthorized' } } })).toBeNull()
    expect(readErrorReason({ response: { data: {} } })).toBeNull()
    expect(readErrorReason(undefined)).toBeNull()
    expect(readErrorReason(new Error('boom'))).toBeNull()
  })
})

describe('applySessionInvalid 决策表', () => {
  beforeEach(() => {
    resetSsoSessionState()
    resetSsoStatusCache()
    mocks.navigateToSso.mockReset()
    mocks.redirectToLogin.mockReset()
  })

  it('非统一票据失效：清会话后回登录页，并带上原始 path+query', () => {
    const action = applySessionInvalid('token_expired', TASKS_RUNTIME)

    expect(action).toBe('login')
    expect(mocks.redirectToLogin).toHaveBeenCalledWith('/tasks?page=2')
    expect(mocks.navigateToSso).not.toHaveBeenCalled()
  })

  it('已经在登录页：什么都不做，避免登录页自己触发死循环', () => {
    const action = applySessionInvalid('iam_session_expired', {
      pathname: '/login',
      search: '?redirect=%2Ftasks',
      ssoEnabled: true
    })

    expect(action).toBe('none')
    expect(mocks.redirectToLogin).not.toHaveBeenCalled()
    expect(mocks.navigateToSso).not.toHaveBeenCalled()
  })

  it('统一票据失效但本部署没开统一认证：仍回登录页', () => {
    const action = applySessionInvalid('iam_session_expired', {
      ...TASKS_RUNTIME,
      ssoEnabled: false
    })

    expect(action).toBe('login')
    expect(mocks.navigateToSso).not.toHaveBeenCalled()
  })

  it('统一票据失效且统一认证启用：顶层跳授权入口，next 为当前地址', () => {
    const action = applySessionInvalid('iam_session_expired', {
      ...TASKS_RUNTIME,
      ssoEnabled: true,
      authorizePath: '/api/v1/auth/sso/authorize'
    })

    expect(action).toBe('sso')
    expect(mocks.navigateToSso).toHaveBeenCalledWith(
      '/api/v1/auth/sso/authorize?next=%2Ftasks%3Fpage%3D2'
    )
    expect(mocks.redirectToLogin).not.toHaveBeenCalled()
  })

  it('同一生命周期只跳一次，复位后可再跳', () => {
    const runtime = {
      ...TASKS_RUNTIME,
      ssoEnabled: true,
      authorizePath: '/api/v1/auth/sso/authorize'
    }

    expect(applySessionInvalid('iam_session_expired', runtime)).toBe('sso')
    expect(applySessionInvalid('iam_session_expired', runtime)).toBe('none')
    expect(mocks.navigateToSso).toHaveBeenCalledTimes(1)

    resetSsoSessionState()
    expect(applySessionInvalid('iam_session_expired', runtime)).toBe('sso')
    expect(mocks.navigateToSso).toHaveBeenCalledTimes(2)
  })

  it('未显式给 ssoEnabled 时从状态缓存取（探测过且启用 → 跳 IAM）', () => {
    writeSsoStatusCache(
      { enabled: true, authorize_path: '/api/v1/auth/sso/authorize', auto_provision: true },
      Date.now()
    )

    expect(applySessionInvalid('iam_session_expired', { pathname: '/tasks', search: '' })).toBe('sso')
  })
})

describe('刷新失败原因的旁路传递', () => {
  beforeEach(() => {
    resetSsoSessionState()
  })

  it('remember 后能 consume 一次，第二次为空（不重复提示）', () => {
    rememberRefreshFailure(iamExpiredError())

    expect(consumeRefreshFailureReason()).toBe('iam_session_expired')
    expect(consumeRefreshFailureReason()).toBeNull()
  })

  it('没有 reason 的错误记住的是 null，不会误判成统一票据失效', () => {
    rememberRefreshFailure(new Error('network down'))

    expect(consumeRefreshFailureReason()).toBeNull()
  })
})
