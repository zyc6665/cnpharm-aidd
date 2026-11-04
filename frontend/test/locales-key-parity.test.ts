import { assert, describe, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import zhCN from '@/locales/zh-CN'
import enUS from '@/locales/en-US'

/**
 * 中英词条必须一一对应。
 *
 * 加语言包时最容易犯的错是只往 zh-CN 里加了键——中文界面正常、英文界面显示
 * 原始 key。这类问题在开发时的中文环境下完全看不出来，只能靠测试兜。
 */
function flatten(value: unknown, prefix = ''): string[] {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return prefix ? [prefix] : []
  }
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    flatten(child, prefix ? `${prefix}.${key}` : key),
  )
}

/** 取某个前缀下的叶子键（用于断言「这个命名空间下两边都有这些键」）。 */
function leavesUnder(messages: unknown, prefix: string): Set<string> {
  const parts = prefix.split('.')
  let cursor: unknown = messages
  for (const part of parts) {
    if (cursor === null || typeof cursor !== 'object') return new Set()
    cursor = (cursor as Record<string, unknown>)[part]
  }
  return new Set(flatten(cursor, prefix))
}

const zhKeys = new Set(flatten(zhCN))
const enKeys = new Set(flatten(enUS))

describe('语言包词条一致性', () => {
  it('中文与英文的叶子键集合完全一致', () => {
    const missingInEn = [...zhKeys].filter((key) => !enKeys.has(key)).sort()
    const missingInZh = [...enKeys].filter((key) => !zhKeys.has(key)).sort()
    assert.deepEqual(missingInEn, [], `英文缺这些键：${missingInEn.slice(0, 20).join(', ')}`)
    assert.deepEqual(missingInZh, [], `中文缺这些键：${missingInZh.slice(0, 20).join(', ')}`)
  })

  it('指标方向提示的键在中英两边都存在', () => {
    const required = [
      'md.result.hints.duration',
      'md.result.hints.temperature',
      'md.result.hints.timestep',
      'screening.detail.hints.score',
      'screening.detail.hints.rmsd',
    ]
    for (const key of required) {
      assert.include([...zhKeys], key, `zh-CN 缺少 ${key}`)
      assert.include([...enKeys], key, `en-US 缺少 ${key}`)
    }
  })

  it('提示词条落在正确的命名空间下（防止插错层级）', () => {
    const zhScreening = leavesUnder(zhCN, 'screening.detail')
    const enScreening = leavesUnder(enUS, 'screening.detail')
    assert.include([...zhScreening], 'screening.detail.hints.score')
    assert.include([...enScreening], 'screening.detail.hints.rmsd')
    // 不该出现在口袋列表命名空间下
    const zhPockets = leavesUnder(zhCN, 'targets.structure.pockets')
    assert.notInclude([...zhPockets], 'targets.structure.pockets.hints.score')
  })

  it('源码中所有 t(\'字面量\') 键都在中英语言包里存在', () => {
    const missing = collectMissingLiteralKeys()
    assert.deepEqual(
      missing,
      [],
      `以下 t() 字面量键在语言包里缺失：\n${missing.slice(0, 40).join('\n')}`,
    )
  })

  it('本次修复涉及的 5 个键在中英两边都存在', () => {
    const required = [
      // 系统设置页标题
      'admin.systemConfig',
      // 工具详情页「缺少必需输入」（带 {inputs} 插值）
      'tasks.missingInputs',
      // 工具详情页参数长度校验（顶层 validation 命名空间）
      'validation.minLength',
      'validation.maxLength',
      // 工作流画布标题回退：改指向已存在键，不新增重复键
      'workflow.workbenchHeader.titleFallback',
    ]
    for (const key of required) {
      assert.include([...zhKeys], key, `zh-CN 缺少 ${key}`)
      assert.include([...enKeys], key, `en-US 缺少 ${key}`)
    }
  })
})

const SRC_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'src')

/**
 * 递归收集 `src/**\/*.{vue,ts}` 里所有 `t('...')` / `$t("...")` 的字面量键。
 *
 * 豁免规则（在注释里说明，避免静默漏检）：
 * - 模板字符串 `` t(`...`) `` 与含 `${...}` 的键：键名在运行时拼接，无法静态展开，
 *   跳过（例如 `` t(`tasks.status.${status}`) ``）。
 * - 非键名形态（含空格、花括号、非标识符字符）的字面量：不是 i18n key，跳过。
 * - 单文件测试（*.spec.ts）与类型声明（*.d.ts）不参与扫描。
 */
function collectMissingLiteralKeys(): string[] {
  const files: string[] = []
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name)
      if (statSync(path).isDirectory()) {
        walk(path)
        continue
      }
      if (!/\.(vue|ts)$/.test(name)) continue
      if (name.endsWith('.spec.ts') || name.endsWith('.d.ts')) continue
      if (path.includes(`${join('src', 'locales')}`)) continue
      files.push(path)
    }
  }
  walk(SRC_DIR)

  const literal = /(?<![A-Za-z0-9_])\$?t\(\s*(['"])([^'"]+)\1/g
  const found = new Map<string, string[]>()
  for (const file of files) {
    const source = readFileSync(file, 'utf8')
    for (const match of source.matchAll(literal)) {
      const key = match[2].trim()
      // 只保留合法的键名形态；模板字符串/含插值的键不会被这条正则匹配到。
      if (!/^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$/.test(key)) continue
      const list = found.get(key) ?? []
      list.push(file)
      found.set(key, list)
    }
  }

  return [...found.keys()]
    .filter((key) => !zhKeys.has(key) || !enKeys.has(key))
    .sort()
}
