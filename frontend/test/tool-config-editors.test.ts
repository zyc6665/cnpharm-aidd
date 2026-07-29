import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  keyValueEntriesToRecord,
  normalizeStringList,
  recordToKeyValueEntries,
  stringListForConfig
} from '../src/utils/tool-config-editors'

test('键值配置应在结构化行与对象之间往返', () => {
  const entries = recordToKeyValueEntries({
    PYTHONPATH: '/app',
    MODEL_PATH: '/models'
  })

  assert.deepEqual(entries, [
    { key: 'PYTHONPATH', value: '/app' },
    { key: 'MODEL_PATH', value: '/models' }
  ])
  assert.deepEqual(keyValueEntriesToRecord(entries), {
    PYTHONPATH: '/app',
    MODEL_PATH: '/models'
  })
})

test('键值配置应忽略全空行并保留值内部空格', () => {
  assert.deepEqual(
    keyValueEntriesToRecord([
      { key: '', value: '' },
      { key: 'LABEL', value: 'lead optimization model' }
    ]),
    { LABEL: 'lead optimization model' }
  )
})

test('键值配置应拒绝缺失键和重复键', () => {
  assert.throws(
    () => keyValueEntriesToRecord([{ key: '', value: 'orphan' }]),
    /配置键不能为空/
  )
  assert.throws(
    () => keyValueEntriesToRecord([
      { key: 'MODEL_PATH', value: '/models/a' },
      { key: ' MODEL_PATH ', value: '/models/b' }
    ]),
    /配置键不能重复: MODEL_PATH/
  )
})

test('字符串列表应保留单项内部空格并过滤空项', () => {
  assert.deepEqual(
    stringListForConfig(['--model-name', 'lead model v2', '  ', '--batch-size', '32']),
    ['--model-name', 'lead model v2', '--batch-size', '32']
  )
})

test('旧字符串列表应兼容归一化，数组配置不拆分单项', () => {
  assert.deepEqual(normalizeStringList('--device cpu --batch-size 32'), [
    '--device',
    'cpu',
    '--batch-size',
    '32'
  ])
  assert.deepEqual(normalizeStringList(['--label', 'lead model']), ['--label', 'lead model'])
})
