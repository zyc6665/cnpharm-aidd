import type { UserInfo } from '@/types/models'
import { EMPTY_DISPLAY } from '@/domain/common/format'

type DisplayableUser = Pick<UserInfo, 'display_name' | 'username' | 'email'>

/**
 * 用户展示名回退链：显示名 → 账号名 → 邮箱前缀 → 空字符串。
 * email 为 null/undefined 时不会抛错，也不会出现 "null"。
 */
export function getUserDisplayName(user: DisplayableUser): string {
  return user.display_name || user.username || (user.email ? user.email.split('@')[0] : '') || ''
}

/** 邮箱列展示：空值统一显示为空值占位符（与全平台一致），避免出现 "null"。 */
export function formatUserEmail(email?: string | null): string {
  return email || EMPTY_DISPLAY
}
