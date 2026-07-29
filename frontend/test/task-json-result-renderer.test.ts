import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  buildJsonResultEntries,
  formatJsonResultLabel,
  formatJsonResultValue
} from '../src/components/tasks/json-result-renderer.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('JSON 结果字段名应转为可读标题', () => {
  assert.equal(formatJsonResultLabel('predicted_affinity'), 'Predicted Affinity')
  assert.equal(formatJsonResultLabel('ligandAtomCount'), 'Ligand Atom Count')
  assert.equal(formatJsonResultLabel('duration-sec'), 'Duration Sec')
})

test('JSON 结果标量值应适合列表阅读', () => {
  assert.equal(formatJsonResultValue(5.280332088470459), '5.2803')
  assert.equal(formatJsonResultValue(41), '41')
  assert.equal(formatJsonResultValue(true), 'True')
  assert.equal(formatJsonResultValue(null), 'None')
})

test('MSIGN 风格输出应生成可递归渲染的分组和数组节点', () => {
  const entries = buildJsonResultEntries({
    success: true,
    message: 'MSIGN affinity prediction completed',
    outputs: {
      prediction: {
        predicted_affinity: 5.280332088470459,
        scale: 'pKa/pKi-like binding affinity score'
      },
      preprocessing: {
        ligand_atom_count: 24,
        pocket_atom_count: 135
      },
      artifacts: [
        {
          name: 'prediction.json',
          path: 'artifacts/prediction.json',
          content_type: 'application/json'
        }
      ]
    },
    metrics: {
      duration_sec: 41,
      model_duration_sec: 37.899
    }
  })

  assert.equal(entries.some(entry => entry.key === 'outputs' && entry.kind === 'object'), true)
  assert.equal(entries.some(entry => entry.key === 'metrics' && entry.kind === 'object'), true)

  const outputsEntry = entries.find(entry => entry.key === 'outputs')
  assert.equal(outputsEntry?.children?.some(entry => entry.key === 'prediction'), true)
  assert.equal(outputsEntry?.children?.some(entry => entry.key === 'artifacts' && entry.kind === 'array'), true)
  assert.equal(outputsEntry?.children?.find(entry => entry.key === 'prediction')?.children?.[0]?.value, '5.2803')
})

test('任务输出摘要应使用通用 JSON 结果渲染器', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/JsonResultRenderer.vue')), true)

  const source = readSource('src/components/tasks/TaskOutputSummary.vue')

  assert.equal(source.includes('JsonResultRenderer'), true)
  assert.equal(source.includes('JSON.stringify(value, null, 2)'), false)
})
