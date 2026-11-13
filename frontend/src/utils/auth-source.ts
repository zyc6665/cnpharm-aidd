/**
 * 认证源（auth_source）的展示规则：文案键、标签颜色、口令托管判定。
 *
 * 全部是纯函数且零依赖：Users 页模板里不再出现 `=== 'ldap'` 这类字面量，新增认证源
 * 只改这一处；入参一律按 `unknown` 收，因为值来自接口，后端将来加枚举也不该让界面崩。
 */

const LABEL_KEYS: Record<string, string> = {
  local: 'admin.authSourceLocal',
  ldap: 'admin.authSourceLdap',
  sso: 'admin.authSourceSso'
}

/** 认证源 → i18n 文案键；未知值回落到「未知」而不是抛错或显示原始 key */
export function authSourceLabelKey(authSource: unknown): string {
  if (typeof authSource !== 'string' || !Object.prototype.hasOwnProperty.call(LABEL_KEYS, authSource)) {
    return 'admin.authSourceUnknown'
  }
  // 索引访问在 noUncheckedIndexedAccess 下仍可能是 undefined，兜一层保证返回 string
  return LABEL_KEYS[authSource] ?? 'admin.authSourceUnknown'
}

/** 认证源 → a-tag 颜色：目录服务金色、统一认证蓝色、本地保持默认灰 */
export function authSourceTagColor(authSource: unknown): 'gold' | 'blue' | 'default' {
  if (authSource === 'ldap') {
    return 'gold'
  }
  if (authSource === 'sso') {
    return 'blue'
  }
  return 'default'
}

/** 口令是否由平台外部的系统托管：ldap 归目录服务，sso 归统一身份认证 */
export function isPasswordManagedExternally(authSource: unknown): boolean {
  return authSource === 'ldap' || authSource === 'sso'
}

/**
 * 「重置口令」被禁用的原因文案键；返回 undefined 表示可重置。
 * 与 isPasswordManagedExternally 同源，避免禁用文案和按钮状态两处判断走偏。
 */
export function resetPasswordDisabledReasonKey(authSource: unknown): string | undefined {
  if (authSource === 'ldap') {
    return 'admin.resetPasswordLdapDisabled'
  }
  if (authSource === 'sso') {
    return 'admin.resetPasswordSsoDisabled'
  }
  return undefined
}
