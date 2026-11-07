import { test } from 'vitest'
import assert from 'node:assert/strict'
import { buildOutputOverview } from './output-summary'

const STANDARD_RESULT = {
  result_version: 'aidd.sciminer/result',
  metrics: { ligand_count: 2, best_affinity_pred_value: -9.5601, failed_count: 0 },
  summary: { note: 'ok', detail: { ignored: true } },
  artifacts: {
    affinity_table: {
      type: 'molecule_table@1',
      files: {
        table: { relative_path: 'artifacts/affinity_results.csv', sha256: 'abc' },
        metadata: { relative_path: 'artifacts/metadata.json' },
      },
    },
    report: {
      metadata: { name: 'Run report' },
      type: 'run_report@1',
      files: [{ relative_path: 'artifacts/report.json' }],
    },
  },
}

test('从标准结果里提取标量指标，跳过嵌套对象', () => {
  const overview = buildOutputOverview(STANDARD_RESULT)
  assert.deepEqual(
    overview.metrics.map((metric) => metric.key),
    ['ligand_count', 'best_affinity_pred_value', 'failed_count', 'note'],
  )
  assert.equal(overview.metrics[1]!.value, '-9.5601')
})

test('产物清单带类型、文件数与主文件', () => {
  const overview = buildOutputOverview(STANDARD_RESULT)
  assert.equal(overview.artifacts.length, 2)
  const table = overview.artifacts[0]!
  assert.equal(table.name, 'Affinity table', '没有可读名时用键名 humanize')
  assert.equal(table.type, 'molecule_table@1')
  assert.equal(table.fileCount, 2)
  assert.equal(table.primaryFile, 'affinity_results.csv')

  const report = overview.artifacts[1]!
  assert.equal(report.name, 'Run report', 'metadata.name 优先')
  assert.equal(report.fileCount, 1)
})

test('产物名缺失时退化可读，不把键名原样丢出来', () => {
  const overview = buildOutputOverview({
    result_version: 'aidd.sciminer/result',
    artifacts: { pocket_residues_json: { files: [] } },
  })
  assert.equal(overview.artifacts[0]!.name, 'Pocket residues json')
  assert.equal(overview.artifacts[0]!.type, '-')
})

test('没有标准结果时返回空概览，不构造假数据', () => {
  assert.deepEqual(buildOutputOverview(null), { metrics: [], artifacts: [] })
  assert.deepEqual(buildOutputOverview('x'), { metrics: [], artifacts: [] })
  assert.deepEqual(buildOutputOverview({ arbitrary: 1 }), { metrics: [], artifacts: [] })
})
