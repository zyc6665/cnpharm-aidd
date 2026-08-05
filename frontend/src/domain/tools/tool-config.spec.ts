import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  formatToolConfigJsonText,
  isToolConfigRecord,
  serializeToolConfigForComparison
} from './tool-config'

test('工具配置 JSON 文本格式化对空值和不可序列化对象使用 fallback', () => {
  assert.equal(formatToolConfigJsonText(null, '{}'), '{}')
  assert.equal(formatToolConfigJsonText({ input: { type: 'string' } }, '{}'), '{\n  "input": {\n    "type": "string"\n  }\n}')

  const circular: Record<string, unknown> = {}
  circular.self = circular
  assert.equal(formatToolConfigJsonText(circular, '{}'), '{}')
})

test('工具配置比较序列化递归排序对象键并保留数组顺序', () => {
  const left = {
    b: 2,
    a: { d: 4, c: 3 },
    list: [{ y: 2, x: 1 }]
  }
  const right = {
    list: [{ x: 1, y: 2 }],
    a: { c: 3, d: 4 },
    b: 2
  }

  assert.equal(serializeToolConfigForComparison(left), serializeToolConfigForComparison(right))
  assert.notEqual(
    serializeToolConfigForComparison({ list: [1, 2] }),
    serializeToolConfigForComparison({ list: [2, 1] })
  )
})

test('工具配置 record 判断排除空值和数组', () => {
  assert.equal(isToolConfigRecord({}), true)
  assert.equal(isToolConfigRecord({ a: 1 }), true)
  assert.equal(isToolConfigRecord(null), false)
  assert.equal(isToolConfigRecord([]), false)
  assert.equal(isToolConfigRecord('value'), false)
})

test('循环配置比较序列化失败时返回空串', () => {
  const circular: Record<string, unknown> = {}
  circular.self = circular
  assert.equal(serializeToolConfigForComparison(circular), '')
})
