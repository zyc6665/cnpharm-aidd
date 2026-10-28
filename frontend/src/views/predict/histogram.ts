/** 直方图分箱（纯函数，便于单测；不依赖 echarts）。 */
export interface HistogramBin {
  label: string
  count: number
}

function formatNumber(value: number): string {
  return Number(value.toFixed(2)).toString()
}

export function buildHistogram(values: number[], binCount = 10): HistogramBin[] {
  const finite = values.filter(value => Number.isFinite(value))
  if (!finite.length) {
    return []
  }

  const count = Math.max(1, Math.floor(binCount))
  const min = Math.min(...finite)
  const max = Math.max(...finite)

  if (min === max) {
    return [{ label: formatNumber(min), count: finite.length }]
  }

  const width = (max - min) / count
  const buckets = Array.from({ length: count }, (_, index) => ({
    start: min + index * width,
    end: min + (index + 1) * width,
    count: 0
  }))

  for (const value of finite) {
    let index = Math.floor((value - min) / width)
    if (index >= count) {
      index = count - 1
    }
    if (index < 0) {
      index = 0
    }
    const bucket = buckets[index]
    if (bucket) {
      bucket.count += 1
    }
  }

  return buckets.map(bucket => ({
    label: `${formatNumber(bucket.start)}–${formatNumber(bucket.end)}`,
    count: bucket.count
  }))
}

/** 判断某列是否为数值列（至少一个非空值，且所有非空值都可解析为有限数字）。 */
export function isNumericColumn(rows: Array<Record<string, string>>, key: string): boolean {
  let seen = 0
  for (const row of rows) {
    const raw = (row[key] ?? '').trim()
    if (!raw) {
      continue
    }
    seen += 1
    if (!Number.isFinite(Number(raw))) {
      return false
    }
  }
  return seen > 0
}

export function toNumericValues(rows: Array<Record<string, string>>, key: string): number[] {
  return rows
    .map(row => Number((row[key] ?? '').trim()))
    .filter(value => Number.isFinite(value))
}
