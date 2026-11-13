import { describe, expect, it } from 'vitest'

import enUS from '@/locales/en-US'
import zhCN from '@/locales/zh-CN'
import {
  authSourceLabelKey,
  authSourceTagColor,
  isPasswordManagedExternally,
  resetPasswordDisabledReasonKey
} from './auth-source'

type Dict = Record<string, unknown>

const zh = zhCN as unknown as Dict
const en = enUS as unknown as Dict
const zhAuth = zh.auth as Dict
const enAuth = en.auth as Dict
const zhAdmin = zh.admin as Dict
const enAdmin = en.admin as Dict
const zhSsoError = zhAuth.ssoError as Dict
const enSsoError = enAuth.ssoError as Dict

// auth 段新增 15 个叶子键 + ssoError 容器本身 = 16 个键（任务单口径）；
// 加上 admin 段 3 个新键，共 19 个。这里把「双语键集合一致」变成机器门禁。
const AUTH_LEAF_KEYS = [
  'ssoLogin',
  'ssoLoginHint',
  'ssoOrLocal',
  'ssoErrorTitle',
  'ssoErrorHint'
] as const

const SSO_ERROR_CODES = [
  'disabled',
  'state',
  'denied',
  'token',
  'userinfo',
  'unavailable',
  'conflict',
  'inactive',
  'not_provisioned',
  'unknown'
] as const

const ADMIN_KEYS = ['authSourceSso', 'authSourceUnknown', 'resetPasswordSsoDisabled'] as const

describe('auth source 文案映射', () => {
  it('三种认证源映射到各自的中英文案键', () => {
    expect(authSourceLabelKey('local')).toBe('admin.authSourceLocal')
    expect(authSourceLabelKey('ldap')).toBe('admin.authSourceLdap')
    expect(authSourceLabelKey('sso')).toBe('admin.authSourceSso')
  })

  it('未知/空认证源回落到通用键而不是抛错', () => {
    expect(authSourceLabelKey(undefined)).toBe('admin.authSourceUnknown')
    expect(authSourceLabelKey(null)).toBe('admin.authSourceUnknown')
    expect(authSourceLabelKey('iam')).toBe('admin.authSourceUnknown')
  })

  it('标签颜色：ldap 金色、sso 蓝色、其余默认', () => {
    expect(authSourceTagColor('ldap')).toBe('gold')
    expect(authSourceTagColor('sso')).toBe('blue')
    expect(authSourceTagColor('local')).toBe('default')
    expect(authSourceTagColor('whatever')).toBe('default')
  })

  it('ldap/sso 的口令由外部系统托管，local 与未知不算', () => {
    expect(isPasswordManagedExternally('ldap')).toBe(true)
    expect(isPasswordManagedExternally('sso')).toBe(true)
    expect(isPasswordManagedExternally('local')).toBe(false)
    expect(isPasswordManagedExternally(undefined)).toBe(false)
  })

  it('重置口令禁用原因：仅外部托管账号返回文案键', () => {
    expect(resetPasswordDisabledReasonKey('ldap')).toBe('admin.resetPasswordLdapDisabled')
    expect(resetPasswordDisabledReasonKey('sso')).toBe('admin.resetPasswordSsoDisabled')
    expect(resetPasswordDisabledReasonKey('local')).toBeUndefined()
    expect(resetPasswordDisabledReasonKey(undefined)).toBeUndefined()
  })
})

describe('统一认证双语文案', () => {
  it('auth 段 15 个新文案键在两种语言下都存在且非空', () => {
    for (const key of AUTH_LEAF_KEYS) {
      expect(typeof zhAuth[key]).toBe('string')
      expect(typeof enAuth[key]).toBe('string')
      expect((zhAuth[key] as string).length).toBeGreaterThan(0)
      expect((enAuth[key] as string).length).toBeGreaterThan(0)
    }
  })

  it('ssoError 覆盖 9 个业务码 + unknown，且双语键集合一致', () => {
    expect(Object.keys(zhSsoError).sort()).toEqual([...SSO_ERROR_CODES].sort())
    expect(Object.keys(enSsoError).sort()).toEqual([...SSO_ERROR_CODES].sort())
    for (const code of SSO_ERROR_CODES) {
      expect((zhSsoError[code] as string).length).toBeGreaterThan(0)
      expect((enSsoError[code] as string).length).toBeGreaterThan(0)
    }
  })

  it('admin 段 3 个新键双语存在且认证源取值正确', () => {
    for (const key of ADMIN_KEYS) {
      expect(typeof zhAdmin[key]).toBe('string')
      expect(typeof enAdmin[key]).toBe('string')
      expect((zhAdmin[key] as string).length).toBeGreaterThan(0)
      expect((enAdmin[key] as string).length).toBeGreaterThan(0)
    }
    expect(zhAdmin.authSourceLocal).toBe('本地账号')
    expect(enAdmin.authSourceLocal).toBe('Local')
    expect(zhAdmin.authSourceSso).toBe('统一认证')
    expect(enAdmin.authSourceSso).toBe('Unified')
  })

  it('新增键集合中英完全一致（防止只改单侧）', () => {
    const zhKeys = [
      ...AUTH_LEAF_KEYS,
      'ssoError',
      ...ADMIN_KEYS
    ].sort()
    const enKeys = [
      ...AUTH_LEAF_KEYS,
      'ssoError',
      ...ADMIN_KEYS
    ].sort()
    expect(zhKeys).toEqual(enKeys)
    for (const key of AUTH_LEAF_KEYS) {
      expect(key in zhAuth).toBe(true)
      expect(key in enAuth).toBe(true)
    }
    expect(Object.keys(zhSsoError).sort()).toEqual(Object.keys(enSsoError).sort())
  })
})
