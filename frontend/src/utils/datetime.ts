/**
 * 服务端时间字符串的解析与展示。
 *
 * 背景：后端所有时间列都是「不带时区的 UTC」（`backend/app/common/time.py` 的
 * `utcnow()` 会 `replace(tzinfo=None)`），序列化出来是 `2026-10-25T13:00:00`
 * 这种没有 `Z`、也没有 `+08:00` 的形态。
 *
 * 而 ECMAScript 的 `new Date('2026-10-25T13:00:00')` **按本地时区解释**，
 * 于是东八区用户看到的每个时间都晚 8 小时——这不是显示格式问题，是错误的时间。
 *
 * 这里统一在解析前补上 `Z`：把「无时区信息」当作 UTC，与后端语义一致。
 * 已经有 `Z` 或 `±hh:mm` 的字符串原样返回，因此对未来的接口改进是安全的。
 */

const NAIVE_DATE_TIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

/**
 * 把服务端时间字符串解析成 `Date`。
 *
 * - 无时区信息 → 视为 UTC（补 `Z`）
 * - 只有日期（`2026-10-25`）→ 视为当天 00:00 UTC
 * - 无法解析 → 返回 `null`，调用方自行决定回退展示
 */
export function parseServerDate(value?: string | null): Date | null {
  if (!value) {
    return null
  }

  const text = value.trim()
  if (!text) {
    return null
  }

  let normalized = text
  if (NAIVE_DATE_TIME.test(text)) {
    normalized = `${text.replace(' ', 'T')}Z`
  } else if (DATE_ONLY.test(text)) {
    normalized = `${text}T00:00:00Z`
  }

  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

/**
 * 按本地时区展示服务端时间。
 *
 * 解析失败时把原样字符串返回——比显示 `Invalid Date` 或 `-` 更容易定位问题。
 */
export function formatServerDateTime(
  value?: string | null,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!value) {
    return '-'
  }

  const date = parseServerDate(value)
  if (!date) {
    return value
  }

  return date.toLocaleString(undefined, options)
}
