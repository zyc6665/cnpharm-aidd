import { describe, expect, it } from 'vitest'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const srcDir = resolve(rootDir, 'src')
const readSource = (relativePath: string) =>
  readFileSync(resolve(rootDir, relativePath), 'utf8')

describe('后端时间戳统一走 parseServerDate（避免 naive UTC 少 8 小时）', () => {
  const auditedFiles = [
    'src/components/workflow/WorkflowRunHistoryPanel.vue',
    'src/composables/useWorkflowPersistence.ts',
    'src/domain/tools/detail-display.ts',
  ]

  for (const file of auditedFiles) {
    it(`${file} 使用 parseServerDate 解析服务端时间`, () => {
      const source = readSource(file)
      assert.equal(source.includes('parseServerDate'), true, `${file} 未使用 parseServerDate`)
    })
  }

  it('源码中不再有 new Date(<服务端字符串>).toLocale... 的直接解析', () => {
    const offenders: string[] = []
    const walk = (dir: string): void => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name)
        if (statSync(path).isDirectory()) {
          walk(path)
          continue
        }
        if (!/\.(vue|ts)$/.test(name)) continue
        if (name.endsWith('.spec.ts') || name.endsWith('.d.ts')) continue
        if (path.endsWith(join('utils', 'datetime.ts'))) continue
        const source = readFileSync(path, 'utf8')
        // new Date(xxx).toLocaleString() / toLocaleDateString()：直接解析后本地化渲染
        if (/new\s+Date\([^)]*\)\s*\.toLocale(?:String|DateString)\(/.test(source)) {
          offenders.push(path.slice(srcDir.length + 1))
        }
      }
    }
    walk(srcDir)

    assert.deepEqual(offenders, [], `以下文件未走 parseServerDate：${offenders.join(', ')}`)
  })
})
