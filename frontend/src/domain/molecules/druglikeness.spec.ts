import { describe, expect, it } from 'vitest'
import {
  classifyMetricTone,
  countLipinskiViolations,
  countRo5Violations,
  druglikenessStars,
  evaluateLipinski,
  hasLipinskiData,
  metricKind,
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
  it('Ro5 只统计四项经典阈值并忽略缺值', () => {
    expect(countRo5Violations(props({ mw: 501, logp: 5, hbd: 6, hba: null, tpsa: 300 }))).toBe(2)
    expect(countRo5Violations(props({ mw: null, logp: null, hbd: null, hba: null }))).toBeNull()
    expect(countRo5Violations(props({ mw: 500, logp: 5, hbd: 5, hba: 10 }))).toBe(0)
  })

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

describe('阈值语义着色 classifyMetricTone', () => {
  it('识别常见列名（key、带单位标题与中文标题）', () => {
    expect(metricKind('mw')).toBe('mw')
    expect(metricKind('MW (Da)')).toBe('mw')
    expect(metricKind('molecular_weight')).toBe('mw')
    expect(metricKind('分子量')).toBe('mw')
    expect(metricKind('XLogP')).toBe('logp')
    expect(metricKind('hbd')).toBe('hbd')
    expect(metricKind('num_h_acceptors')).toBe('hba')
    expect(metricKind('TPSA')).toBe('tpsa')
    expect(metricKind('qed')).toBe('qed')
    expect(metricKind('lipinski_violations')).toBe('violations')
    expect(metricKind('rotatable_bonds')).toBe('rotatable')
    expect(metricKind('docking_score')).toBeNull()
    expect(metricKind('')).toBeNull()
  })

  it('按上限 / 下限给绿、琥珀、红三档', () => {
    expect(classifyMetricTone('mw', 420)).toBe('good')
    expect(classifyMetricTone('mw', '550')).toBe('warn')
    expect(classifyMetricTone('mw', 700)).toBe('bad')

    expect(classifyMetricTone('logp', 4.2)).toBe('good')
    expect(classifyMetricTone('logp', 5.5)).toBe('warn')
    expect(classifyMetricTone('logp', 7)).toBe('bad')

    expect(classifyMetricTone('hbd', 3)).toBe('good')
    expect(classifyMetricTone('hbd', 6)).toBe('warn')
    expect(classifyMetricTone('hbd', 9)).toBe('bad')

    expect(classifyMetricTone('hba', 8)).toBe('good')
    expect(classifyMetricTone('hba', 11)).toBe('warn')
    expect(classifyMetricTone('hba', 13)).toBe('bad')

    expect(classifyMetricTone('tpsa', 120)).toBe('good')
    expect(classifyMetricTone('tpsa', 150)).toBe('warn')
    expect(classifyMetricTone('tpsa', 180)).toBe('bad')
  })

  it('QED / 越界条数 / 可旋转键按方向判定', () => {
    expect(classifyMetricTone('qed', 0.72)).toBe('good')
    expect(classifyMetricTone('qed', 0.42)).toBe('warn')
    expect(classifyMetricTone('qed', 0.1)).toBe('bad')

    expect(classifyMetricTone('lipinski_violations', 0)).toBe('good')
    expect(classifyMetricTone('lipinski_violations', 1)).toBe('warn')
    expect(classifyMetricTone('lipinski_violations', 3)).toBe('bad')

    expect(classifyMetricTone('rotatable_bonds', 6)).toBe('good')
    expect(classifyMetricTone('rotatable_bonds', 11)).toBe('warn')
    expect(classifyMetricTone('rotatable_bonds', 15)).toBe('bad')
  })

  it('缺失值与未知列保持中性（null），绝不把「未计算」染红', () => {
    expect(classifyMetricTone('mw', null)).toBeNull()
    expect(classifyMetricTone('mw', '')).toBeNull()
    expect(classifyMetricTone('mw', '-')).toBeNull()
    expect(classifyMetricTone('mw', 'N/A')).toBeNull()
    expect(classifyMetricTone('score', 0.1)).toBeNull()
    expect(classifyMetricTone('', 500)).toBeNull()
  })
})
