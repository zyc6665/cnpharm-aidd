import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工具创建编辑页应复用统一标题并保留返回操作', () => {
  const source = readSource('src/views/tools/Create.vue')

  assert.equal(source.includes('AppPageHeader'), true)
  assert.equal(source.includes('<template #actions>'), true)
  assert.equal(source.includes('@click="goBack"'), true)
  assert.equal(source.includes('class="page-header"'), false)
  assert.equal(source.includes('.page-header'), false)
})

test('工具创建编辑页表单应提供移动端栅格兜底', () => {
  const source = readSource('src/views/tools/Create.vue')

  assert.equal(source.includes('class="tool-form"'), true)
  assert.equal(source.includes(':deep(.tool-form .ant-col-12)'), true)
  assert.equal(source.includes(':deep(.tool-form .ant-col-8)'), true)
  assert.equal(source.includes(':deep(.tool-form .ant-col-16)'), true)
})

test('工具执行配置应提供可复用的结构化键值和列表编辑器', () => {
  const keyValuePath = resolve(rootDir, 'src/components/tools/StructuredKeyValueEditor.vue')
  const stringListPath = resolve(rootDir, 'src/components/tools/StructuredStringListEditor.vue')

  assert.equal(existsSync(keyValuePath), true)
  assert.equal(existsSync(stringListPath), true)

  const keyValueSource = readFileSync(keyValuePath, 'utf8')
  const stringListSource = readFileSync(stringListPath, 'utf8')

  for (const marker of [
    'modelValue',
    "'update:modelValue'",
    'addEntry',
    'removeEntry',
    'DeleteOutlined',
    'aria-label',
    'structured-key-value-row',
    '@media (max-width:'
  ]) {
    assert.equal(keyValueSource.includes(marker), true, `missing key/value marker ${marker}`)
  }

  for (const marker of [
    'modelValue',
    "'update:modelValue'",
    'addItem',
    'removeItem',
    'DeleteOutlined',
    'aria-label',
    'structured-string-list-row',
    '@media (max-width:'
  ]) {
    assert.equal(stringListSource.includes(marker), true, `missing list marker ${marker}`)
  }
})

test('工具创建页应以结构化数据编辑全部执行器 map 和 list 字段', () => {
  const source = readSource('src/views/tools/Create.vue')

  for (const marker of [
    'StructuredKeyValueEditor',
    'StructuredStringListEditor',
    'v-model="apiHeaderEntries"',
    'v-model="dockerCommandItems"',
    'v-model="dockerEnvEntries"',
    'v-model="pythonArgumentItems"',
    'v-model="sshEnvEntries"',
    'v-model="sshOutputGlobItems"',
    'recordToKeyValueEntries',
    'keyValueEntriesToRecord',
    'normalizeStringList',
    'stringListForConfig'
  ]) {
    assert.equal(source.includes(marker), true, `missing structured field marker ${marker}`)
  }

  for (const removedMarker of [
    'apiHeadersText',
    'dockerEnvText',
    'sshEnvText',
    'sshOutputGlobsText'
  ]) {
    assert.equal(source.includes(removedMarker), false, `legacy JSON field remains: ${removedMarker}`)
  }
})

test('工具创建页应突出 Tool Package v2 主路径并标记旧语义映射为兼容项', () => {
  const source = readSource('src/views/tools/Create.vue')
  const domain = readSource('src/domain/tools/agent-capability.ts')
  const toolConfigDomain = readSource('src/domain/tools/tool-config.ts')

  for (const marker of [
    'tool-package-primary-path',
    'Tool Package v2',
    '平台标准 Artifact 输入/输出槽',
    '旧版 Agent 语义映射（兼容）',
    '输入语义映射（兼容）',
    '输出语义映射（兼容）',
    'binding_pocket@1',
    'ligand_structure@1'
  ]) {
    assert.equal(source.includes(marker), true, `missing unified contract marker ${marker}`)
  }

  assert.equal(source.includes("from '@/domain/tools'"), true)
  assert.equal(source.includes('parseAgentCapabilityForm'), true)
  assert.equal(source.includes('buildAgentCapabilityConfig'), true)
  assert.equal(source.includes('serializeToolConfigForComparison'), true)
  assert.equal(domain.includes('isAgentCapabilityFormComplete'), true)
  assert.equal(toolConfigDomain.includes('formatToolConfigJsonText'), true)
})
