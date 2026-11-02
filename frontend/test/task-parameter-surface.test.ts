import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const ROOT = resolve(__dirname, '..')

function read(relativePath: string): string {
  return readFileSync(resolve(ROOT, relativePath), 'utf-8')
}

test('任务详情用参数表组件渲染，不再按键名原样平铺', () => {
  const detail = read('src/views/tasks/Detail.vue')
  assert.ok(detail.includes('TaskParameterTable'), '详情页应引入参数表组件')
  assert.ok(
    detail.includes(':schema="parameterSchema"'),
    '参数表必须拿到工具版本的 parameters_schema',
  )
  assert.equal(
    detail.includes('v-for="(value, key) in task.inputs?.params"'),
    false,
    '不应保留按原始键值平铺的旧实现',
  )
})

test('参数表组件从 schema 派生分组，并保留原始 JSON 入口', () => {
  const component = read('src/components/tasks/TaskParameterTable.vue')
  assert.ok(component.includes('buildParameterGroups'))
  assert.ok(component.includes('tasks.parameters.rawJson'), '排障时仍要能看到提交原值')
  assert.ok(component.includes('data-testid="task-parameter-table"'))
})

test('分组与占位文案在中英两份 locale 里同时存在', () => {
  const requiredKeys = [
    'parameters',
    'group',
    'dockingBox',
    'reproducibility',
    'unset',
    'defaultPrefix',
    'rawJson',
    'empty',
  ]
  for (const localeFile of ['src/locales/zh-CN/index.ts', 'src/locales/en-US/index.ts']) {
    const source = read(localeFile)
    for (const key of requiredKeys) {
      assert.ok(
        new RegExp(`\\b${key}:`).test(source),
        `${localeFile} 缺少 tasks.parameters.${key}`,
      )
    }
  }
})

test('参数可读化只在前端做，不改后端契约', () => {
  const domain = read('src/domain/tasks/parameters.ts')
  assert.equal(domain.includes('api/tasks'), false, '展示层不应回写接口')
  const detailApi = read('src/api/tasks.ts')
  assert.equal(
    detailApi.includes('parameters_schema'),
    false,
    '后端返回的是工具 config，前端不应另开参数接口',
  )
})
