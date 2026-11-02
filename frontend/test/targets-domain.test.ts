import { test } from 'vitest'
import assert from 'node:assert/strict'

import {
  buildStructurePreviewArtifact,
  findSelectedPocket,
  formatPlddtMean,
  plddtBand,
  formatSourceType,
  formatTargetType,
  formatPocketCenter,
  formatTargetDateTime,
  pickStructureFile,
  pocketScoreTone,
  resolveTargetErrorMessage,
  sortPocketsByScore,
} from '../src/domain/targets'
import type { PocketSummary, ProteinStructureDetail, StructureFileLink } from '../src/types/targets'

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
    // 后端 serialize_* 输出的是 naive UTC（不带 Z），fixture 必须照抄真实形态，
    // 否则时间戳解析回归（B1）在 TZ=UTC 下永远测不出来。
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  }
}

function makeStructure(overrides: Partial<ProteinStructureDetail> = {}): ProteinStructureDetail {
  return {
    id: 'structure-1',
    protein_id: 'protein-1',
    source_type: 'PREDICTED',
    structure_urn: 'file:file-1',
    structure_file_id: 'file-1',
    prepared_urn: null,
    prepared_file_id: null,
    pdbqt_urn: null,
    pdbqt_file_id: null,
    sha256: 'abc123',
    plddt_mean: 87.456,
    plddt_urn: null,
    plddt_file_id: null,
    model: { name: 'boltz-2', version: '1.0' },
    tool: { name: 'boltz-2', version: '1.0' },
    task_id: 'task-1',
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
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

// 说明：口袋「选定」是后端维护的同结构内互斥状态（POST /pockets/{id}:select 会连带
// 把同结构下其余口袋置为未选），前端因此不做本地 patch 而是选定后整表重拉（见 Pockets.vue
// 的 handleSelect）。这条用例只锁定 `findSelectedPocket` 的「唯一即有效、否则视为脏数据」
// 语义，供页面在重拉窗口期展示一致的状态。
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

test('formatTargetDateTime 把后端 naive UTC 当 UTC 解析，带 Z 与不带 Z 结果一致', () => {
  // 这条断言与运行时区无关：两种写法指向同一瞬时，格式化结果必须相同。
  // 时区归一化由共享的 `@/utils/datetime` 负责（PR6 收敛），此处只验证靶点域接上了它。
  assert.equal(
    formatTargetDateTime('2026-10-25T13:00:00'),
    formatTargetDateTime('2026-10-25T13:00:00Z'),
  )
  assert.equal(formatTargetDateTime('2026-10-25T13:00:00'), new Date('2026-10-25T13:00:00Z').toLocaleString())
})

test('formatTargetDateTime 对空值与不可解析值给出稳定输出', () => {
  assert.equal(formatTargetDateTime(null), '-')
  assert.equal(formatTargetDateTime(undefined), '-')
  assert.equal(formatTargetDateTime(''), '-')
  assert.equal(formatTargetDateTime('not-a-date'), 'not-a-date')
})

test('formatPlddtMean 保留两位小数，缺失或非法值返回占位符', () => {
  assert.equal(formatPlddtMean(87.456), '87.46')
  assert.equal(formatPlddtMean(0), '0.00')
  assert.equal(formatPlddtMean(null), '-')
  assert.equal(formatPlddtMean(undefined), '-')
  assert.equal(formatPlddtMean(Number.NaN), '-')
})

test('pickStructureFile 优先命中 preferred 角色，其次回落到任一可下载文件，全无返回 null', () => {
  const files: StructureFileLink[] = [
    { role: 'pdbqt', file_id: 'file-pdbqt', urn: 'file:file-pdbqt', download_url: '/api/v1/files/file-pdbqt/download' },
    { role: 'structure', file_id: 'file-structure', urn: 'file:file-structure', download_url: '/api/v1/files/file-structure/download' },
  ]

  assert.equal(pickStructureFile(files)?.file_id, 'file-structure', '默认优先 structure')
  assert.equal(
    pickStructureFile(files, ['pdbqt'])?.file_id,
    'file-pdbqt',
    '显式 preferredRoles 应生效',
  )
  assert.equal(
    pickStructureFile(files, ['prepared'])?.file_id,
    'file-structure',
    'preferred 全部落空时按默认优先级（structure → prepared → pdbqt）兜底，而不是按清单顺序',
  )
  assert.equal(pickStructureFile([]), null)
  assert.equal(
    pickStructureFile([{ role: 'structure', file_id: 'x', urn: null, download_url: '' }]),
    null,
    '没有 download_url 的文件不可用于预览',
  )
})

test('buildStructurePreviewArtifact 组装出 StructureArtifactPreview 需要的 artifact', () => {
  const files: StructureFileLink[] = [
    { role: 'structure', file_id: 'file-1', urn: 'file:file-1', download_url: '/api/v1/files/file-1/download' },
  ]

  const artifact = buildStructurePreviewArtifact(makeStructure(), files)

  assert.ok(artifact)
  assert.equal(artifact.id, 'structure-1')
  assert.equal(artifact.artifact_type, 'protein_structure')
  assert.equal(artifact.latest_version.files?.length, 1)
  assert.equal(artifact.latest_version.files?.[0].download_url, '/api/v1/files/file-1/download')
  assert.equal(artifact.latest_version.files?.[0].is_primary, true)
  assert.equal(
    artifact.latest_version.filename,
    'structure-1-structure.pdb',
    '结构文件按角色推断扩展名',
  )
  assert.equal(artifact.sha256 ?? artifact.latest_version.sha256, 'abc123')

  assert.equal(
    buildStructurePreviewArtifact(makeStructure(), []),
    null,
    '没有任何可用文件时返回 null，页面回落到空态',
  )
})

test('resolveTargetErrorMessage 优先取后端 message，其次 Error.message，最后 fallback', () => {
  assert.equal(
    resolveTargetErrorMessage(
      { response: { data: { message: '蛋白缺少序列，无法提交结构预测' } } },
      '提交失败',
    ),
    '蛋白缺少序列，无法提交结构预测',
  )
  assert.equal(resolveTargetErrorMessage(new Error('boom'), '提交失败'), 'boom')
  assert.equal(resolveTargetErrorMessage({}, '提交失败'), '提交失败')
  assert.equal(resolveTargetErrorMessage(null, '提交失败'), '提交失败')
  assert.equal(resolveTargetErrorMessage({ response: { data: { message: '   ' } } }, '提交失败'), '提交失败')
})

test('formatSourceType 把结构来源枚举翻成中文，未知值原样透出', () => {
  assert.equal(formatSourceType('PREDICTED'), '预测')
  assert.equal(formatSourceType('IMPORTED'), '导入')
  assert.equal(formatSourceType('PREPARED'), '预处理')
  // 未知枚举宁可露出原始值，也不要吞成 '-' 让人以为是空数据
  assert.equal(formatSourceType('SYNTHETIC'), 'SYNTHETIC')
  assert.equal(formatSourceType(null), '-')
})

test('formatTargetType 把靶点类型枚举翻成中文', () => {
  assert.equal(formatTargetType('PROTEIN'), '蛋白')
  assert.equal(formatTargetType('RNA'), 'RNA')
  assert.equal(formatTargetType(undefined), '-')
})

test('pLDDT 分档按 AlphaFold 口径给出四档，缺值时不分档', () => {
  assert.equal(plddtBand(95), 'veryHigh')
  assert.equal(plddtBand(90), 'veryHigh')
  assert.equal(plddtBand(89.9), 'confident')
  assert.equal(plddtBand(70), 'confident')
  assert.equal(plddtBand(69.9), 'low')
  assert.equal(plddtBand(50), 'low')
  assert.equal(plddtBand(49.9), 'veryLow')
  assert.equal(plddtBand(null), null)
  assert.equal(plddtBand(undefined), null)
  assert.equal(plddtBand(Number.NaN), null)
})

test('pLDDT 数字本身仍保留两位小数，档位只是补充文字', () => {
  assert.equal(formatPlddtMean(87.3456), '87.35')
  assert.equal(formatPlddtMean(87.3449), '87.34')
  assert.equal(formatPlddtMean(null), '-')
})
