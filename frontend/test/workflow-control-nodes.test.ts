import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  ADDABLE_WORKFLOW_CONTROL_NODE_TYPES,
  createWorkflowControlNodeDefaults,
  resolveWorkflowControlNodeTitleKey,
} from '../src/workflow/control-nodes.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('控制节点定义应集中声明可添加类型和默认配置', () => {
  assert.deepEqual(ADDABLE_WORKFLOW_CONTROL_NODE_TYPES, ['condition', 'map'])

  assert.deepEqual(createWorkflowControlNodeDefaults('condition'), {
    titleKey: 'workflow.controlNodes.condition.title',
    descriptionKey: 'workflow.controlNodes.condition.description',
    expression: { op: '==', left: true, right: true },
  })

  assert.deepEqual(createWorkflowControlNodeDefaults('map'), {
    titleKey: 'workflow.controlNodes.map.title',
    descriptionKey: 'workflow.controlNodes.map.description',
    over: 'workflow_input:smiles_csv',
    max_parallelism: 4,
  })
})

test('控制节点标题 fallback 应返回稳定 locale key', () => {
  assert.equal(resolveWorkflowControlNodeTitleKey('condition'), 'workflow.controlNodes.condition.title')
  assert.equal(resolveWorkflowControlNodeTitleKey('map'), 'workflow.controlNodes.map.title')
  assert.equal(resolveWorkflowControlNodeTitleKey('loop'), 'workflow.controlNodes.loop.title')
  assert.equal(resolveWorkflowControlNodeTitleKey('custom-control'), 'custom-control')
})

test('控制节点调用方应复用集中定义而不是硬编码中文', () => {
  const storeSource = readSource('src/stores/workflow.ts')
  const persistenceSource = readSource('src/composables/useWorkflowPersistence.ts')
  const paletteSource = readSource('src/components/workflow/WorkflowControlNodePalette.vue')

  assert.equal(storeSource.includes('@/workflow/control-nodes'), true)
  assert.equal(persistenceSource.includes('resolveWorkflowControlNodeTitleKey'), true)
  assert.equal(paletteSource.includes('ADDABLE_WORKFLOW_CONTROL_NODE_TYPES'), true)
  assert.equal(paletteSource.includes('useI18n'), true)

  for (const source of [storeSource, persistenceSource, paletteSource]) {
    assert.equal(source.includes("'条件分支'"), false)
    assert.equal(source.includes("'批量处理'"), false)
    assert.equal(source.includes("'循环优化'"), false)
  }
})
