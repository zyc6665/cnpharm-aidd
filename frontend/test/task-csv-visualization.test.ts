import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  detectCsvResultFile,
  detectSmilesColumn,
  parseCsvPreview
} from '../src/components/tasks/csv-result.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('CSV 结果规则模块与结果表格组件应存在', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/csv-result.ts')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/CsvResultViewer.vue')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/Smiles2DCell.vue')), true)
})

test('detectCsvResultFile 应识别 csv 扩展名和 text/csv 内容类型', () => {
  assert.equal(
    detectCsvResultFile({
      filename: 'result.csv',
      content_type: 'text/csv',
      url: '/api/v1/files/1/download'
    })?.filename,
    'result.csv'
  )

  assert.equal(
    detectCsvResultFile({
      filename: 'result.tsv',
      content_type: 'text/plain',
      url: '/api/v1/files/2/download'
    }),
    null
  )
})

test('parseCsvPreview 应保留 CSV 行列并识别常规 smiles 表头', () => {
  const preview = parseCsvPreview('SMILES,Predicted_Label\\nCCO,0\\nCCN,1\\n')

  assert.deepEqual(preview.columns.map(column => column.key), ['SMILES', 'Predicted_Label'])
  assert.equal(preview.rows.length, 2)
  assert.equal(preview.smilesColumnKey, 'SMILES')
  assert.equal(preview.rows[0]?.SMILES, 'CCO')
})

test('parseCsvPreview 应能从空表头但内容像 smiles 的列中识别结构列', () => {
  const preview = parseCsvPreview(',Predicted_Label\\nCCO,0\\nCCC,1\\n')

  assert.equal(preview.columns[0]?.key, 'column_1')
  assert.equal(preview.smilesColumnKey, 'column_1')
  assert.equal(preview.rows[0]?.column_1, 'CCO')
})

test('detectSmilesColumn 在没有可信分子列时应返回 null', () => {
  const smilesColumnKey = detectSmilesColumn(
    ['name', 'score'],
    [
      { name: 'sample-1', score: '0.3' },
      { name: 'sample-2', score: '0.8' }
    ]
  )

  assert.equal(smilesColumnKey, null)
})

test('CSV viewer 源码应使用滚动表格和 2D 分子单元格组件', () => {
  const viewerSource = readSource('src/components/tasks/CsvResultViewer.vue')
  const smilesCellSource = readSource('src/components/tasks/Smiles2DCell.vue')
  const panelSource = readSource('src/components/tasks/ResultVisualizationPanel.vue')

  assert.equal(viewerSource.includes('scroll'), true)
  assert.equal(viewerSource.includes('Smiles2DCell'), true)
  assert.equal(smilesCellSource.includes('smiles-drawer'), true)
  assert.equal(panelSource.includes('CsvResultViewer'), true)
})
