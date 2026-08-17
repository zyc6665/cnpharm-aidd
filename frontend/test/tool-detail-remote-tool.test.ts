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

  for (const marker of [
    'remote-tool-info',
    'isRemoteToolV1',
    'remote_tool_v1',
    'manifest_sha256',
    'last_smoke_test',
    'remoteToolSmokeTaskId',
    '`/tasks/${remoteToolSmokeTaskId}`',
    'remoteToolSmokeStatusColor',
    'smoke test'
  ]) {
    assert.equal(source.includes(marker), true, `missing remote detail marker ${marker}`)
  }
})
