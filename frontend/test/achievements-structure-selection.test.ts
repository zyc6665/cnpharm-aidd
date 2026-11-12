import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  sortStructuresByNewest,
  structureOptionLabel
} from '@/domain/targets/structure-option'
import type { ProteinStructureDetail } from '@/types/targets'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

function structure(overrides: Partial<ProteinStructureDetail>): ProteinStructureDetail {
  return {
    id: '7965989e-1e1c-4981-8cec-ac5d3e8f165e',
    protein_id: 'protein-1',
    source_type: 'PREDICTED',
    structure_urn: 'file:abc',
    structure_file_id: 'abc',
    prepared_urn: null,
    prepared_file_id: null,
    pdbqt_urn: null,
    pdbqt_file_id: null,
    sha256: null,
    plddt_mean: 83.04,
    plddt_urn: null,
    plddt_file_id: null,
    model: { id: 'm1', name: 'boltz2-structure-prediction' } as ProteinStructureDetail['model'],
    tool: { id: 't1', name: 'Boltz-2' } as ProteinStructureDetail['tool'],
    task_id: null,
    created_at: '2026-11-11T02:35:59.094453Z',
    updated_at: null,
    ...overrides
  } as ProteinStructureDetail
}

test('结构下拉文案区分来源、模型、pLDDT、准备状态与时间', () => {
  const predicted = structureOptionLabel(structure({}))
  assert.match(predicted, /^预测结构 · boltz2-structure-prediction/)
  assert.match(predicted, /pLDDT 83\.0/)
  assert.match(predicted, /（7965989e）$/)
  // 未准备的结构不写「已准备」，否则用户无法判断坐标能否直接对接。
  assert.equal(predicted.includes('已准备'), false)

  const prepared = structureOptionLabel(
    structure({ source_type: 'PREPARED', prepared_urn: 'file:prepared', plddt_mean: null })
  )
  assert.match(prepared, /^准备结构/)
  assert.match(prepared, /已准备/)
  assert.equal(prepared.includes('pLDDT'), false)

  const imported = structureOptionLabel(
    structure({ source_type: 'IMPORTED', model: null, tool: null, created_at: null })
  )
  assert.match(imported, /^导入结构/)
  assert.equal(imported.includes('· ·'), false)
})

test('结构按创建时间倒序，最新的排第一但旧结构仍在列表里', () => {
  const older = structure({ id: 'aaaa1111-0000-0000-0000-000000000000', created_at: '2026-11-11T02:35:59Z' })
  const newer = structure({ id: 'bbbb2222-0000-0000-0000-000000000000', created_at: '2026-11-11T12:12:24Z' })

  assert.deepEqual(
    sortStructuresByNewest([older, newer]).map((item) => item.id.slice(0, 4)),
    ['bbbb', 'aaaa']
  )
  // 不修改入参数组：调用方可能还在用它做计数。
  const original = [older, newer]
  sortStructuresByNewest(original)
  assert.deepEqual(original.map((item) => item.id.slice(0, 4)), ['aaaa', 'bbbb'])
})

test('成果页提供结构选择器，切换后重新拉取口袋与坐标', () => {
  const page = readSource('src/views/demo/Achievements.vue')

  assert.match(page, /data-testid="structure-select"/)
  assert.match(page, /v-model:value="structureId"/)
  assert.match(page, /@change="handleStructureChange"/)
  // 默认取最新，但必须经过排序函数，而不是直接信任后端顺序
  assert.match(page, /structures\.value = sortStructuresByNewest\(/)
  // 切换结构要清掉上一个结构的口袋/残基，再用新 id 重新加载
  assert.match(page, /async function handleStructureChange\(value: unknown\)/)
  assert.match(page, /await Promise\.all\(\[loadPockets\(nextId\), loadPdb\(nextId\)\]\)/)
  // 该结构没有口袋时要有明确说明，而不是一句「暂无数据」
  assert.match(page, /data-testid="pocket-empty-state"/)
  assert.match(page, /口袋是按结构预测的/)
})
