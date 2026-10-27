import dayjs from 'dayjs'

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

/**
 * 固定格式的本地时间展示。
 *
 * 为什么不用 `dayjs(value).format(...)`：dayjs 与 `new Date()` 一样把无时区字符串
 * 当本地时间，东八区下会比真实时刻早 8 小时，且与 `formatServerDateTime` 的口径
 * 打架——同一个平台里工作台显示 08:23、靶点列表显示 16:23，用户会以为其中一处是错的。
 * 这里统一「先按 UTC 解析，再按本地时区渲染」，两处口径由此一致。
 */
function formatLocal(value: string | null | undefined, template: string): string {
  if (!value) {
    return '-'
  }

  const date = parseServerDate(value)
  if (!date) {
    return value
  }

  return dayjs(date).format(template)
}

/** `2026-10-27 16:23` —— 表格与详情页的默认粒度。 */
export function formatDateTimeMinutes(value?: string | null): string {
  return formatLocal(value, 'YYYY-MM-DD HH:mm')
}

/** `2026-10-27 16:23:06` —— 需要秒的场景（任务起止时间、日志锚点）。 */
export function formatDateTimeSeconds(value?: string | null): string {
  return formatLocal(value, 'YYYY-MM-DD HH:mm:ss')
}

/** `10-27 16:23` —— 卡片/列表里的紧凑粒度，省掉年份。 */
export function formatMonthDayMinutes(value?: string | null): string {
  return formatLocal(value, 'MM-DD HH:mm')
}

/** `16:23:06.412` —— 任务日志行的时间戳。 */
export function formatClockWithMillis(value?: string | null): string {
  return formatLocal(value, 'HH:mm:ss.SSS')
}

/** `2026-10-27` —— 只到日的场景（注册时间、审计日期）。 */
export function formatDateOnly(value?: string | null): string {
  return formatLocal(value, 'YYYY-MM-DD')
}
