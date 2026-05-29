import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  buildFocusedVisualizationScene,
  buildVisualizationScene
} from '../src/components/tasks/result-visualization.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('任务结果可视化组件与规则模块应存在', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/ResultVisualizationPanel.vue')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/MoleculeViewer.vue')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/result-visualization.ts')), true)
})

test('任务详情页应接入结果可视化面板', () => {
  const detailSource = readSource('src/views/tasks/Detail.vue')

  assert.equal(detailSource.includes('ResultVisualizationPanel'), true)
  assert.equal(detailSource.includes('result-visualization'), true)
})

test('结果可视化规则应覆盖首批结构与小分子格式', () => {
  const rulesSource = readSource('src/components/tasks/result-visualization.ts')

  assert.equal(rulesSource.includes('.pdb'), true)
  assert.equal(rulesSource.includes('.cif'), true)
  assert.equal(rulesSource.includes('.mmcif'), true)
  assert.equal(rulesSource.includes('.pdbqt'), true)
  assert.equal(rulesSource.includes('.sdf'), true)
  assert.equal(rulesSource.includes('.mol2'), true)
})

test('多输出三维结果应保留固定输入并支持逐项切换输出', () => {
  const scene = buildVisualizationScene({
    id: 'task-1',
    tool_id: 'tool-1',
    status: 'success',
    progress: 100,
    created_at: '2026-05-28T00:00:00Z',
    input_files: [
      {
        id: 'input-1',
        original_name: 'pocket.pdb',
        content_type: 'chemical/x-pdb',
        url: '/api/v1/files/input-1/download'
      }
    ],
    output_files: [
      {
        id: 'output-1',
        original_name: 'pose_1.sdf',
        content_type: 'chemical/x-mdl-sdfile',
        url: '/api/v1/files/output-1/download'
      },
      {
        id: 'output-2',
        original_name: 'pose_2.sdf',
        content_type: 'chemical/x-mdl-sdfile',
        url: '/api/v1/files/output-2/download'
      }
    ]
  })

  assert.equal(scene.inputEntries.length, 1)
  assert.equal(scene.outputEntries.length, 2)
  assert.equal(scene.selectedOutputKey, scene.outputEntries[0]?.key || null)
  assert.deepEqual(
    scene.entries.map(entry => entry.key),
    [scene.inputEntries[0]?.key, scene.outputEntries[0]?.key]
  )

  const switchedScene = buildFocusedVisualizationScene(scene, scene.outputEntries[1]?.key)

  assert.equal(switchedScene.selectedOutputKey, scene.outputEntries[1]?.key || null)
  assert.deepEqual(
    switchedScene.entries.map(entry => entry.key),
    [scene.inputEntries[0]?.key, scene.outputEntries[1]?.key]
  )
})

test('结果面板源码应包含输出结果列表选择逻辑', () => {
  const panelSource = readSource('src/components/tasks/ResultVisualizationPanel.vue')

  assert.equal(panelSource.includes('selectedOutputKey'), true)
  assert.equal(panelSource.includes('scene.outputEntries'), true)
})
