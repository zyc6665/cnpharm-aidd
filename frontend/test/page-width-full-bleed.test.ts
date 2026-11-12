import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, it } from 'vitest'

const ROOT = resolve(process.cwd())

function views(dir = join(ROOT, 'src/views')): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      out.push(...views(full))
    } else if (entry.endsWith('.vue')) {
      out.push(full)
    }
  }
  return out
}

/**
 * 页面根容器的宽度必须走共享 token。
 * 之前 28 个页面各自写 960~1440px 的上限，宽屏下内容区空出大半，同一套页面在不同模块宽度还不一致。
 */
describe('业务页面铺满内容区', () => {
  it('共享 token 存在且为铺满', () => {
    const variables = readFileSync(join(ROOT, 'src/assets/styles/variables.less'), 'utf8')
    assert.match(variables, /@page-max-width:\s*none;/)
    assert.match(variables, /@field-grid-min:\s*\d+px;/)
  })

  it('页面根容器不再写死像素宽度', () => {
    const offenders: string[] = []
    for (const file of views()) {
      const text = readFileSync(file, 'utf8')
      // 形如 `.design-page { ... max-width: 960px; ... }`
      const pattern = /\.[a-z0-9-]*-page\s*\{[^}]*max-width:\s*([^;]+);/gi
      for (const match of text.matchAll(pattern)) {
        const value = (match[1] ?? '').trim()
        if (/^\d+px$/.test(value)) {
          offenders.push(`${file.replace(ROOT, '')} -> max-width: ${value}`)
        }
      }
    }
    assert.deepEqual(offenders, [], `页面根容器仍在限制宽度：\n${offenders.join('\n')}`)
  })

  it('多字段表单用自适应网格，宽屏不挤在左侧', () => {
    const molecule = readFileSync(join(ROOT, 'src/views/design/MoleculeGeneration.vue'), 'utf8')
    const peptide = readFileSync(join(ROOT, 'src/views/design/PeptideDesign.vue'), 'utf8')
    for (const source of [molecule, peptide]) {
      assert.match(source, /grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(@field-grid-min,\s*1fr\)\)/)
    }
    // 上传区不能再被 560px 的正文宽度限制住
    assert.doesNotMatch(molecule, /\.source-body\s*\{[^}]*max-width:\s*560px/)
  })
})
