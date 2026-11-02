import { assert, describe, it } from 'vitest'
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
})
