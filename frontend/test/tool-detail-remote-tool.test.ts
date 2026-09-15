import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工具详情页应展示 remote-tool.v1 自注册运行状态', () => {
  const source = readSource('src/views/tools/Detail.vue')
  const sidebarSource = readSource('src/components/tools/ToolDetailSidebar.vue')
  const presentationSource = readSource('src/composables/useToolDetailPresentation.ts')

  assert.equal(source.includes('ToolDetailSidebar'), true)
  for (const marker of [
    'remote-tool-info',
    'remote_tool_v1',
    'manifest_sha256',
    'remoteToolSmokeTaskId',
    'remoteToolSmokeError',
    '`/tasks/${remoteToolSmokeTaskId}`',
    'remoteToolSmokeStatusColor',
    '失败原因',
    'smoke test'
  ]) {
    assert.equal(sidebarSource.includes(marker), true, `missing remote detail marker ${marker}`)
  }

  assert.equal(source.includes('isRemoteToolV1'), true)

  for (const marker of [
    'last_smoke_test',
    "status === 'scheduled'",
    "status === 'stale'",
    '已排队',
    'Manifest 已变更',
    'remoteToolSmokeStatusText'
  ]) {
    assert.equal(presentationSource.includes(marker), true, `missing remote presentation marker ${marker}`)
  }
})
