import { describe, expect, it } from 'vitest'
import { formatServerDateTime, parseServerDate } from './datetime'

describe('parseServerDate', () => {
  it('把无时区的服务端时间当作 UTC 解析', () => {
    // 后端 `utcnow()` 返回 naive UTC，序列化后没有 Z。若按本地时区解析，
    // 东八区用户看到的每个时间都会晚 8 小时。
    expect(parseServerDate('2026-10-25T13:00:00')?.toISOString()).toBe(
      '2026-10-25T13:00:00.000Z'
    )
  })

  it('接受空格分隔的 naive 时间', () => {
    expect(parseServerDate('2026-10-25 13:00:00')?.toISOString()).toBe(
      '2026-10-25T13:00:00.000Z'
    )
  })

  it('已经带时区的时间原样解析', () => {
    expect(parseServerDate('2026-10-25T13:00:00Z')?.toISOString()).toBe(
      '2026-10-25T13:00:00.000Z'
    )
    expect(parseServerDate('2026-10-25T21:00:00+08:00')?.toISOString()).toBe(
      '2026-10-25T13:00:00.000Z'
    )
  })

  it('只有日期时按当天 00:00 UTC', () => {
    expect(parseServerDate('2026-10-25')?.toISOString()).toBe('2026-10-25T00:00:00.000Z')
  })

  it('空值与非法值返回 null', () => {
    expect(parseServerDate(undefined)).toBeNull()
    expect(parseServerDate(null)).toBeNull()
    expect(parseServerDate('   ')).toBeNull()
    expect(parseServerDate('not-a-date')).toBeNull()
  })
})

describe('formatServerDateTime', () => {
  it('空值显示占位符', () => {
    expect(formatServerDateTime(undefined)).toBe('-')
    expect(formatServerDateTime('')).toBe('-')
  })

  it('非法值原样返回，便于定位问题', () => {
    expect(formatServerDateTime('not-a-date')).toBe('not-a-date')
  })

  it('合法时间按本地时区展示且与解析结果一致', () => {
    const formatted = formatServerDateTime('2026-10-25T13:00:00Z')
    expect(formatted).not.toBe('-')
    expect(formatted).toBe(new Date('2026-10-25T13:00:00Z').toLocaleString())
  })
})
