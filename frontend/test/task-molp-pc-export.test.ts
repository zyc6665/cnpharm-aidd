import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  buildMolpPcCsv,
  selectMolpPcCsvSourceFile
} from '../src/components/tasks/molp-pc-export.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('MolP-Pc CSV 导出模块应存在', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/molp-pc-export.ts')), true)
})

test('selectMolpPcCsvSourceFile 应优先选择 QED ranked metadata CSV', () => {
  const source = selectMolpPcCsvSourceFile([
    {
      filename: 'artifacts/metadata.csv',
      content_type: 'text/csv',
      url: '/api/v1/files/metadata/download'
    },
    {
      filename: 'artifacts/qed_ranked_metadata.csv',
      content_type: 'text/csv',
      url: '/api/v1/files/ranked/download'
    }
  ])

  assert.equal(source?.filename, 'artifacts/qed_ranked_metadata.csv')
})

test('buildMolpPcCsv 应从 smiles 列导出 MolP-Pc 可直接读取的单列 CSV', () => {
  const csv = [
    'rank,index,smiles,sdf_file,qed',
    '1,67,CCO,SDF/62.sdf,0.93',
    '2,48,c1ccccc1,SDF/45.sdf,0.92'
  ].join('\n')

  assert.equal(buildMolpPcCsv(csv), 'SMILES\nCCO\nc1ccccc1\n')
})

test('buildMolpPcCsv 应处理需要 CSV 转义的 SMILES 值', () => {
  const csv = [
    'SMILES,score',
    '"C[C@H](N)C(=O)O",1',
    '"C1=CC=CC=C1",0.8'
  ].join('\n')

  assert.equal(buildMolpPcCsv(csv), 'SMILES\nC[C@H](N)C(=O)O\nC1=CC=CC=C1\n')
})

test('buildMolpPcCsv 在缺少 SMILES 列时应返回 null', () => {
  assert.equal(buildMolpPcCsv('name,score\nmol1,0.5\n'), null)
})

test('任务输出摘要应接入 MolP-Pc CSV 导出按钮', () => {
  const source = readSource('src/components/tasks/TaskOutputSummary.vue')

  assert.equal(source.includes('exportMolpPcCsv'), true)
  assert.equal(source.includes('canExportMolpPcCsv'), true)
  assert.equal(source.includes('tasks.exportMolpPcCsv'), true)
})
