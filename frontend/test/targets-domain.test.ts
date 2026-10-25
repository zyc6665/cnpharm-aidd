import { test } from 'vitest'
import assert from 'node:assert/strict'

import {
  findSelectedPocket,
  formatPocketCenter,
  pocketScoreTone,
  sortPocketsByScore,
} from '../src/domain/targets'
import type { PocketSummary } from '../src/types/targets'

function makePocket(overrides: Partial<PocketSummary> = {}): PocketSummary {
  return {
    id: 'pocket-1',
    structure_id: 'structure-1',
    rank: 1,
    score: -6.5,
    volume: 120.5,
    center: { x: 1, y: 2, z: 3 },
    box_size: { x: 10, y: 10, z: 10 },
    residue_count: 12,
    selected: false,
    tool: { name: 'fpocket', version: '4.1' },
    task_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

test('sortPocketsByScore 按 score 降序返回新数组，score 为 null 的排到末尾', () => {
  const pockets = [
    makePocket({ id: 'null-score', score: null }),
    makePocket({ id: 'low', score: -5.2 }),
    makePocket({ id: 'high', score: -9.4 }),
    makePocket({ id: 'mid', score: -7.1 }),
  ]

  const sorted = sortPocketsByScore(pockets)

  assert.deepEqual(
    sorted.map((pocket) => pocket.id),
    ['low', 'mid', 'high', 'null-score'],
  )
  assert.deepEqual(
    pockets.map((pocket) => pocket.id),
    ['null-score', 'low', 'high', 'mid'],
    'sortPocketsByScore 不应就地修改入参数组',
  )
})

test('findSelectedPocket 仅在恰好一个口袋 selected 时返回该口袋', () => {
  const pockets = [makePocket({ id: 'a' }), makePocket({ id: 'b' }), makePocket({ id: 'c' })]

  assert.equal(findSelectedPocket(pockets), null, '无选定时返回 null')

  const single = pockets.map((pocket) =>
    pocket.id === 'b' ? { ...pocket, selected: true } : pocket,
  )
  assert.equal(findSelectedPocket(single)?.id, 'b')

  const duplicated = pockets.map((pocket) => ({ ...pocket, selected: true }))
  assert.equal(
    findSelectedPocket(duplicated),
    null,
    '选定不唯一时必须返回 null 而不是任意挑一个',
  )
})

test('formatPocketCenter 按三位小数格式化坐标，缺失时给出占位符', () => {
  assert.equal(formatPocketCenter({ x: 1.23456, y: -2.5, z: 0 }), '1.235, -2.500, 0.000')
  assert.equal(formatPocketCenter({ x: null, y: null, z: null }), '-')
  assert.equal(formatPocketCenter(null), '-')
  assert.equal(formatPocketCenter(undefined), '-')
})

test('pocketScoreTone 按 -8 / -6 分成 strong / medium / weak 三档', () => {
  assert.equal(pocketScoreTone(-9.2), 'strong')
  assert.equal(pocketScoreTone(-8), 'strong')
  assert.equal(pocketScoreTone(-7.4), 'medium')
  assert.equal(pocketScoreTone(-6), 'medium')
  assert.equal(pocketScoreTone(-5.9), 'weak')
  assert.equal(pocketScoreTone(0), 'weak')
})

test('空数组下三个域函数给出稳定结果', () => {
  assert.deepEqual(sortPocketsByScore([]), [])
  assert.equal(findSelectedPocket([]), null)
})

test('score 为 null 或 undefined 时归入 weak 档', () => {
  assert.equal(pocketScoreTone(null), 'weak')
  assert.equal(pocketScoreTone(undefined), 'weak')
})
