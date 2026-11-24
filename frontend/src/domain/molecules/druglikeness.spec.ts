import { describe, expect, it } from 'vitest'
import {
  countLipinskiViolations,
  druglikenessStars,
  evaluateLipinski,
  hasLipinskiData,
  type LipinskiProperties,
} from './druglikeness'

function props(overrides: Partial<LipinskiProperties> = {}): LipinskiProperties {
  return {
    mw: 320,
    logp: 2.1,
    hbd: 2,
    hba: 4,
    tpsa: 70,
    qed: null,
    ...overrides,
  }
}

describe('Lipinski 五规则评估', () => {
  it('全部在上限内时通过，比例按上限归一化', () => {
    const rules = evaluateLipinski(props())
    expect(rules).toHaveLength(5)
    expect(rules.every(rule => rule.passed === true)).toBe(true)
    expect(rules.find(rule => rule.id === 'mw')?.ratio).toBeCloseTo(320 / 500)
    expect(rules.find(rule => rule.id === 'tpsa')?.ratio).toBeCloseTo(70 / 140)
  })

  it('越界维度标红所需的 passed=false，并统计越界数量', () => {
    const value = props({ mw: 780, logp: 6.4, tpsa: 180 })
    const rules = evaluateLipinski(value)
    expect(rules.find(rule => rule.id === 'mw')?.passed).toBe(false)
    expect(rules.find(rule => rule.id === 'logp')?.passed).toBe(false)
    expect(rules.find(rule => rule.id === 'tpsa')?.passed).toBe(false)
    expect(countLipinskiViolations(value)).toBe(3)
  })

  it('缺值不当作越界，比例回退到 0', () => {
    const rules = evaluateLipinski(props({ mw: null, logp: null, hbd: null, hba: null, tpsa: null }))
    expect(rules.every(rule => rule.passed === null)).toBe(true)
    expect(rules.every(rule => rule.ratio === 0)).toBe(true)
    expect(countLipinskiViolations(props({ mw: null }))).toBe(0)
  })

  it('没有任何性质数据时 hasLipinskiData 为 false', () => {
    expect(hasLipinskiData(props({ mw: null, logp: null, hbd: null, hba: null, tpsa: null }))).toBe(false)
    expect(hasLipinskiData(props())).toBe(true)
  })
})

describe('类药性星级', () => {
  it('有 QED 时按 QED 映射到 1~5 星', () => {
    expect(druglikenessStars(props({ qed: 0.92 }))).toBe(5)
    expect(druglikenessStars(props({ qed: 0.5 }))).toBe(3)
    expect(druglikenessStars(props({ qed: 0.05 }))).toBe(1)
  })

  it('没有 QED 时按越界条数回退', () => {
    expect(druglikenessStars(props())).toBe(5)
    expect(druglikenessStars(props({ mw: 900, logp: 9 }))).toBe(3)
  })

  it('完全无数据时不伪造星级', () => {
    expect(druglikenessStars(props({ mw: null, logp: null, hbd: null, hba: null, tpsa: null }))).toBeNull()
    expect(druglikenessStars(null)).toBeNull()
  })
})
