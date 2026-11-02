import { describe, expect, it } from 'vitest'
import {
  EMPTY_DISPLAY,
  formatNullable,
  formatNumber,
  formatWithUnit,
  humanizeKey,
} from './format'

describe('formatNullable', () => {
  it('空值统一显示为占位符', () => {
    expect(formatNullable(null)).toBe(EMPTY_DISPLAY)
    expect(formatNullable(undefined)).toBe(EMPTY_DISPLAY)
    expect(formatNullable('')).toBe(EMPTY_DISPLAY)
    expect(formatNullable('   ')).toBe(EMPTY_DISPLAY)
  })

  it('布尔用调用方给的文案，未给则退化为 true/false 而不是中文', () => {
    expect(formatNullable(true, { yes: '是', no: '否' })).toBe('是')
    expect(formatNullable(false, { yes: '是', no: '否' })).toBe('否')
    expect(formatNullable(true)).toBe('true')
  })

  it('NaN / Infinity 不显示成 NaN', () => {
    expect(formatNullable(Number.NaN)).toBe(EMPTY_DISPLAY)
    expect(formatNullable(Number.POSITIVE_INFINITY)).toBe(EMPTY_DISPLAY)
  })

  it('0 必须显示为 0 而不是占位符', () => {
    expect(formatNullable(0)).toBe('0')
  })
})

describe('formatNumber', () => {
  it('保留小数位但去掉多余的零', () => {
    expect(formatNumber(0.1, 2)).toBe('0.1')
    expect(formatNumber(3, 2)).toBe('3')
    expect(formatNumber(1.2345, 2)).toBe('1.23')
    expect(formatNumber(1.005, 1)).toBe('1')
  })

  it('非数值交给 formatNullable', () => {
    expect(formatNumber(null)).toBe(EMPTY_DISPLAY)
    expect(formatNumber('12.5')).toBe('12.5')
  })
})

describe('formatWithUnit', () => {
  it('有效值拼单位', () => {
    expect(formatWithUnit(8.123, 'kcal/mol')).toBe('8.12 kcal/mol')
    expect(formatWithUnit(1.5, 'Å')).toBe('1.5 Å')
  })

  it('空值不输出「- 单位」这种半截文案', () => {
    expect(formatWithUnit(null, 'Å')).toBe(EMPTY_DISPLAY)
  })

  it('单位为空时只给数字', () => {
    expect(formatWithUnit(7, '')).toBe('7')
  })
})

describe('humanizeKey', () => {
  it('下划线转空格并首字母大写', () => {
    expect(humanizeKey('sampling_steps')).toBe('Sampling steps')
    expect(humanizeKey('box_size_x')).toBe('Box size x')
    expect(humanizeKey('pdb-id')).toBe('Pdb id')
  })

  it('空键名给占位符而不是空串', () => {
    expect(humanizeKey('')).toBe(EMPTY_DISPLAY)
  })
})
