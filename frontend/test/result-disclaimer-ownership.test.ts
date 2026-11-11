import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const srcDir = resolve(rootDir, 'src')

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return walk(full)
    return full.endsWith('.vue') ? [full] : []
  })
}

/** 把 `@/x` 与相对引用都解析成 src 下的绝对路径（不带扩展名也认）。 */
function resolveImport(fromFile: string, specifier: string): string | null {
  const base = specifier.startsWith('@/')
    ? resolve(srcDir, specifier.slice(2))
    : specifier.startsWith('.')
      ? resolve(dirname(fromFile), specifier)
      : null
  if (!base) return null
  return base.endsWith('.vue') ? base : `${base}.vue`
}

function rendersDisclaimer(source: string): boolean {
  return /<ResultDisclaimer\s*\/?>/.test(source)
}

function importedComponents(file: string, source: string): string[] {
  const found: string[] = []
  const pattern = /import\s+[^'"]*?from\s+['"]([^'"]+)['"]/g
  let match = pattern.exec(source)
  while (match) {
    const resolved = resolveImport(file, match[1])
    if (resolved) found.push(resolved)
    match = pattern.exec(source)
  }
  return found
}

test('免责声明由页面自己渲染，嵌套的结果面板不再重复', () => {
  // 曾经的现场：Result → PropertyPredictResult → MoleculePredictDetail →
  // AffinityPredictDetail 四层各放一条，用户在同一页看到三遍。
  // 规则：渲染声明的组件不得再引用另一个渲染声明的组件（子树互不重叠）。
  const files = walk(srcDir)
  const sources = new Map(files.map((file) => [file, readFileSync(file, 'utf8')]))

  const duplicates: string[] = []
  for (const file of files) {
    const source = sources.get(file)!
    if (!rendersDisclaimer(source)) continue
    for (const child of importedComponents(file, source)) {
      const childSource = sources.get(child)
      if (childSource && rendersDisclaimer(childSource)) {
        duplicates.push(`${relative(rootDir, file)} → ${relative(rootDir, child)}`)
      }
    }
  }

  assert.deepEqual(duplicates, [], `页面与其嵌套组件都渲染了免责声明：\n${duplicates.join('\n')}`)
})

test('结果页每一层都至少有一处渲染免责声明', () => {
  // 分发壳（Result.vue）自己不渲染：它只决定用哪个结果面板，声明由面板负责，
  // 否则面板那条会被算成第二处重复。
  const expectRendered = [
    'src/views/tasks/StructureTaskResult.vue',
    'src/views/tasks/PocketTaskResult.vue',
    'src/views/tasks/GenericTaskResult.vue',
    'src/views/predict/PropertyPredictResult.vue',
    'src/views/design/GenerationResults.vue',
    'src/views/screening/ScreenResult.vue',
    'src/views/md/MdResult.vue',
    'src/views/md/FreeEnergyResult.vue'
  ]
  const expectSilent = [
    'src/views/tasks/Result.vue',
    'src/views/predict/MoleculePredictDetail.vue',
    'src/views/predict/AffinityPredictDetail.vue'
  ]

  for (const file of expectRendered) {
    const source = readFileSync(resolve(rootDir, file), 'utf8')
    assert.equal(rendersDisclaimer(source), true, file)
  }
  for (const file of expectSilent) {
    const source = readFileSync(resolve(rootDir, file), 'utf8')
    assert.equal(rendersDisclaimer(source), false, file)
  }
})
