import { describe, expect, it } from 'vitest'

import {
  IAM_SESSION_EXPIRED_REASON,
  LOGIN_PATH,
  SSO_AUTHORIZE_FALLBACK_PATH,
  buildSsoAuthorizeUrl,
  isLoginLocation,
  navigateToSso,
  resolveCurrentLocation,
  resolveNextPath,
  sanitizeNextPath,
  ssoErrorKey
} from './sso'

describe('resolveNextPath：next 白名单', () => {
  it('站内路径原样保留（含查询串）', () => {
    expect(resolveNextPath('/tasks?page=2')).toBe('/tasks?page=2')
    expect(resolveNextPath('/workspace')).toBe('/workspace')
  })

  it('拒绝开放重定向：协议、协议相对、反斜杠、非斜杠开头', () => {
    for (const bad of [
      'https://evil.invalid/tasks',
      '//evil.invalid/tasks',
      '/\\evil.invalid',
      '\\evil.invalid',
      'tasks',
      '',
      '   '
    ]) {
      expect(resolveNextPath(bad)).toBe('/workspace')
    }
  })

  it('拒绝控制字符与超长路径（对齐后端 _safe_local_path 的 512 上限）', () => {
    expect(resolveNextPath('/tasks\nX-Injected: 1')).toBe('/workspace')
    expect(resolveNextPath('/tasks\r\n')).toBe('/workspace')
    expect(resolveNextPath('/tasks\u0000')).toBe('/workspace')
    expect(resolveNextPath(`/tasks?q=${'a'.repeat(600)}`)).toBe('/workspace')
  })

  it('拒绝回到登录页，否则 SSO 回流会成环', () => {
    expect(resolveNextPath('/login')).toBe('/workspace')
    expect(resolveNextPath('/login?redirect=/tasks')).toBe('/workspace')
    expect(resolveNextPath('/login#sso_error=conflict')).toBe('/workspace')
    expect(resolveNextPath('/login/')).toBe('/workspace')
  })

  it('非字符串入参不抛错，一律回落', () => {
    expect(resolveNextPath(undefined)).toBe('/workspace')
    expect(resolveNextPath(null)).toBe('/workspace')
    expect(resolveNextPath(['/tasks'])).toBe('/workspace')
    expect(resolveNextPath({ path: '/tasks' })).toBe('/workspace')
  })

  it('sanitizeNextPath 对非法值返回空串，供调用方区分「没给」和「给了但非法」', () => {
    expect(sanitizeNextPath('/tasks')).toBe('/tasks')
    expect(sanitizeNextPath('//evil.invalid')).toBe('')
    expect(sanitizeNextPath('/login')).toBe('')
  })
})

describe('resolveCurrentLocation / isLoginLocation', () => {
  it('把 pathname 与 search 拼成可回填的站内地址', () => {
    expect(resolveCurrentLocation('/tasks', '?page=2')).toBe('/tasks?page=2')
    expect(resolveCurrentLocation('/tasks', 'page=2')).toBe('/tasks?page=2')
    expect(resolveCurrentLocation('/tasks')).toBe('/tasks')
    expect(resolveCurrentLocation('/', '')).toBe('/')
  })

  it('识别登录页，用于避免在登录页再跳一次', () => {
    expect(isLoginLocation(LOGIN_PATH)).toBe(true)
    expect(isLoginLocation('/login/')).toBe(true)
    expect(isLoginLocation('/tasks')).toBe(false)
    expect(isLoginLocation('/login-help')).toBe(false)
  })

  it('会话失效原因是后端约定的常量', () => {
    expect(IAM_SESSION_EXPIRED_REASON).toBe('iam_session_expired')
    expect(LOGIN_PATH).toBe('/login')
  })
})

describe('buildSsoAuthorizeUrl', () => {
  it('默认拼出「授权入口 + 编码后的 next」', () => {
    expect(buildSsoAuthorizeUrl(SSO_AUTHORIZE_FALLBACK_PATH, '/tasks?page=2')).toBe(
      '/api/v1/auth/sso/authorize?next=%2Ftasks%3Fpage%3D2'
    )
  })

  it('apiBase 为空、/api/v1、/api/v1/ 三种写法结果一致且不透出 api/v1/api/v1', () => {
    const variants = ['', '/api/v1', '/api/v1/'].map(apiBase =>
      buildSsoAuthorizeUrl('/api/v1/auth/sso/authorize', '/tasks', apiBase)
    )
    expect(new Set(variants).size).toBe(1)
    expect(variants[0]).toBe('/api/v1/auth/sso/authorize?next=%2Ftasks')
    expect(variants[0]).not.toContain('/api/v1/api/v1')
  })

  it('authorize_path 已被拼成双前缀时只保留一层', () => {
    expect(
      buildSsoAuthorizeUrl('/api/v1/api/v1/auth/sso/authorize', '/tasks', '/api/v1')
    ).toBe('/api/v1/auth/sso/authorize?next=%2Ftasks')
  })

  it('authorize_path 为空或为相对路径时回退/补前导斜杠', () => {
    expect(buildSsoAuthorizeUrl(null, '/tasks')).toBe(
      '/api/v1/auth/sso/authorize?next=%2Ftasks'
    )
    expect(buildSsoAuthorizeUrl('', '/tasks')).toBe('/api/v1/auth/sso/authorize?next=%2Ftasks')
    expect(buildSsoAuthorizeUrl('auth/sso/authorize', '/tasks', '/api/v1')).toBe(
      '/api/v1/auth/sso/authorize?next=%2Ftasks'
    )
  })

  it('next 里的非法值不会带进授权地址', () => {
    expect(buildSsoAuthorizeUrl(SSO_AUTHORIZE_FALLBACK_PATH, '/login')).toBe(
      '/api/v1/auth/sso/authorize?next=%2Fworkspace'
    )
    expect(buildSsoAuthorizeUrl(SSO_AUTHORIZE_FALLBACK_PATH, '//evil.invalid')).toBe(
      '/api/v1/auth/sso/authorize?next=%2Fworkspace'
    )
  })
})

describe('ssoErrorKey', () => {
  it('9 个业务码映射到 auth.ssoError.<code>', () => {
    for (const code of [
      'disabled',
      'state',
      'denied',
      'token',
      'userinfo',
      'unavailable',
      'conflict',
      'inactive',
      'not_provisioned'
    ]) {
      expect(ssoErrorKey(code)).toBe(`auth.ssoError.${code}`)
    }
  })

  it('未知码与非字符串入参回落到通用文案', () => {
    expect(ssoErrorKey('weird')).toBe('auth.ssoError.unknown')
    expect(ssoErrorKey(undefined)).toBe('auth.ssoError.unknown')
    expect(ssoErrorKey(null)).toBe('auth.ssoError.unknown')
    expect(ssoErrorKey(['conflict'])).toBe('auth.ssoError.unknown')
  })
})

describe('navigateToSso', () => {
  it('是全仓唯一的顶层跳转出口（jsdom 的 location.assign 不可 forge，只断言可调用）', () => {
    expect(typeof navigateToSso).toBe('function')
  })
})
