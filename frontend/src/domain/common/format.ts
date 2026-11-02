/**
 * 跨领域的显示格式化原语。
 *
 * 只做「值 → 人能读的字符串」，不做业务判断、不带领域知识。
 * 之前的做法是每个详情页各写一份 `formatDate` / `formatPropertyValue` /
 * `formatPlddtMean`，同一个数字在不同页可能保留不同位数、同一个空值在不同页
 * 可能是 `-` 或 `—` 或空白。这里收敛成一处，页面只负责取字段。
 */

export const EMPTY_DISPLAY = '-'

export interface NullableOptions {
  /** 布尔真值文案（默认 是 / 否 由调用方通过 i18n 传入） */
  yes?: string
  no?: string
}

/** 空值统一显示为 `-`；布尔按调用方给的文案；其余 `String(value)`。 */
export function formatNullable(value: unknown, options: NullableOptions = {}): string {
  if (value === null || value === undefined) {
    return EMPTY_DISPLAY
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed === '' ? EMPTY_DISPLAY : trimmed
  }
  if (typeof value === 'boolean') {
    return value ? options.yes ?? 'true' : options.no ?? 'false'
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : EMPTY_DISPLAY
  }
  return String(value)
}

/** 数值保留小数位，去掉多余的 0；非数值原样交给 formatNullable。 */
export function formatNumber(value: unknown, digits = 2): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return formatNullable(value)
  }
  const fixed = value.toFixed(digits)
  // 0.100 → 0.1；3.00 → 3
  return fixed.includes('.') ? fixed.replace(/\.?0+$/, '') : fixed
}

/** 数值 + 单位；值无效时只给 `-`，不输出「- Å」。 */
export function formatWithUnit(value: unknown, unit: string, digits = 2): string {
  const formatted = formatNumber(value, digits)
  if (formatted === EMPTY_DISPLAY) {
    return EMPTY_DISPLAY
  }
  return unit ? `${formatted} ${unit}` : formatted
}

/**
 * 下划线/中划线键名转可读文案：`sampling_steps` → `Sampling steps`。
 * 这是「没有中文词表时的兜底」，比直接显示裸键名好，但不如人工词表。
 */
export function humanizeKey(key: string): string {
  const cleaned = key.replace(/[_-]+/g, ' ').trim()
  if (cleaned === '') {
    return EMPTY_DISPLAY
  }
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1)
}
