import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * 靶点删除入口的回归网。
 *
 * 背景（用户 m46945「我新建靶点之后为什么不能删除？」）：后端
 * `DELETE /api/v1/targets/{id}` 与 `deleteTarget` 客户端从建表起就存在，
 * 但列表页的操作列只放了「查看详情」——**能力在、入口不在**，用户看到的是
 * 「这个平台不能删靶点」。这类缺口不会被类型检查或接口测试抓到，
 * 只能在页面上点一次，所以这里守住入口本身。
 *
 * 另外三条约束是删靶点这件事本身要求的：
 *   1. 必须二次确认，并把连带删除的范围写清楚（蛋白/结构/口袋/残基）；
 *   2. 删除过程要防连点，否则第二次请求拿到 404 会把「删掉了」变成报错；
 *   3. 删完要留痕（`AuditAction.DELETE` + `ResourceType.TARGET` + 行数）。
 */

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = resolve(rootDir, '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

function readBackendSource(relativePath: string): string {
  return readFileSync(resolve(repoRoot, relativePath), 'utf8')
}

test('靶点列表的操作列里有删除按钮，并走二次确认', () => {
  const page = readSource('src/views/targets/List.vue')

  assert.match(page, /import \{ createTarget, deleteTarget, listTargets \} from '@\/api\/targets'/)
  assert.match(page, /data-testid="target-delete-button"/)
  assert.match(page, /<a-popconfirm/)
  assert.match(page, /:title="t\('targets\.list\.deleteConfirm', \{ name: record\.name \}\)"/)
  // 连带删除的范围要写在确认框里，否则用户以为只删一行
  assert.match(page, /:description="t\('targets\.list\.deleteConfirmContent'\)"/)
  assert.match(page, /@confirm="handleDelete\(record\)"/)

  assert.match(page, /async function handleDelete\(record: TargetSummary\)/)
  assert.match(page, /await deleteTarget\(record\.id\)/)
  // 防连点：第一个请求在途时后续点击直接返回
  assert.match(page, /if \(deletingId\.value !== null\) \{/)
  // 删掉当页最后一条要回退一页
  assert.match(page, /if \(targets\.value\.length === 1 && page\.value > 1\) \{/)
})

test('删除失败要给出可读提示，而不是静默什么都不发生', () => {
  const page = readSource('src/views/targets/List.vue')
  assert.match(page, /resolveTargetErrorMessage\(cause, t\('targets\.list\.deleteFailed'\)\)/)
  assert.match(page, /message\.success\(t\('targets\.list\.deleteSuccess', \{ name: record\.name \}\)\)/)
})

test('中英文两套文案都有删除相关键', () => {
  for (const locale of ['zh-CN', 'en-US']) {
    const source = readSource(`src/locales/${locale}/index.ts`)
    for (const key of [
      'deleteConfirm:',
      'deleteConfirmContent:',
      'deleteSuccess:',
      'deleteFailed:'
    ]) {
      assert.ok(source.includes(key), `${locale} 缺少 ${key}`)
    }
  }
})

test('后端有删除端点且记录删除审计与行数', () => {
  const api = readBackendSource('backend/app/api/v1/targets.py')
  assert.match(api, /@router\.delete\("\/targets\/\{target_id\}"/)
  assert.match(api, /record_domain_delete\(/)
  assert.match(api, /resource_type=ResourceType\.TARGET/)
  // 名字快照要在删除前取：删完之后 ORM 对象已经过期
  assert.match(api, /target_name = str\(target\.name\)/)

  const service = readBackendSource('backend/app/services/domain_targets.py')
  assert.match(service, /async def delete_target_cascade\(db: AsyncSession, \*, target_id: str\) -> dict\[str, int\]/)
  for (const key of ['proteins', 'structures', 'pockets', 'pocketResidues']) {
    assert.ok(service.includes(`"${key}"`), `删除计数缺少 ${key}`)
  }

  const enums = readBackendSource('backend/app/common/enums.py')
  assert.match(enums, /TARGET = "target"/)

  const generated = readSource('src/types/enums.generated.ts')
  // 断言落在 RESOURCE_TYPE 数组内部，而不是「数组以 target 结尾」——
  // 后面再加资源类型（例如 project）不该让这条守护测试失败。
  assert.match(generated, /RESOURCE_TYPE = \[[^\]]*"target"[^\]]*\] as const/)
})

test('deleteTarget 客户端指向单个靶点资源', () => {
  const client = readSource('src/api/targets.ts')
  assert.match(client, /export const deleteTarget = \(targetId: string\) =>/)
  assert.match(client, /del<.*>\(`\/targets\/\$\{targetId\}`/)
})
