import { assert, describe, it } from 'vitest'
import { createI18n } from 'vue-i18n'
import zhCN from '@/locales/zh-CN'
import enUS from '@/locales/en-US'

/**
 * 语言包必须整包可编译：任何一条消息编译失败，页面在渲染那一刻就抛错。
 *
 * vue-i18n 的 `{` 是插值起点，文案里的 JSON 示例（如 `{"pic50": 7.2}`）必须写成
 * 字面量块 `{'...'}`。写错的代价远大于「显示原始 key」：`t()` 在渲染函数里抛异常，
 * 组件整块不渲染——表现为按钮点了没反应（决策记录抽屉就是这样整片消失的）。
 *
 * `locales-key-parity` 只比键名，`locales-browser-guard` 只看源码字符串，
 * 都发现不了这种「有键但编不出来」的情况，所以单独用一条用例把两种语言全量扫一遍。
 */

/** 把语言包拍平成「点分路径 → 字符串」，非字符串叶子（数组等）不参与编译。 */
function flattenStrings(value: unknown, prefix = ''): Array<[string, string]> {
  if (typeof value === 'string') {
    return prefix ? [[prefix, value]] : []
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return []
  }
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    flattenStrings(child, prefix ? `${prefix}.${key}` : key)
  )
}

/** 逐条编译，返回 `key: 错误信息` 列表；空数组表示整包可用。 */
function collectCompileErrors(messages: Record<string, unknown>): string[] {
  const i18n = createI18n({
    legacy: false,
    locale: 'probe',
    // 关掉告警，避免几千条「缺参数」的警告把输出刷满；这里只关心编译异常。
    missingWarn: false,
    fallbackWarn: false
  })
  i18n.global.setLocaleMessage('probe', messages)

  const failures: string[] = []
  for (const [key] of flattenStrings(messages)) {
    try {
      i18n.global.t(key)
    } catch (cause) {
      const reason = cause instanceof Error ? cause.message.split('\n')[0] : String(cause)
      failures.push(`${key}: ${reason}`)
    }
  }
  return failures
}

describe('语言包消息编译', () => {
  it('zh-CN 的每条消息都能编译', () => {
    assert.deepEqual(collectCompileErrors(zhCN), [])
  })

  it('en-US 的每条消息都能编译', () => {
    assert.deepEqual(collectCompileErrors(enUS), [])
  })

  it('JSON 示例类文案按字面量输出，不会被当成插值', () => {
    const i18n = createI18n({
      legacy: false,
      locale: 'zh-CN',
      messages: { 'zh-CN': zhCN }
    })
    assert.equal(i18n.global.t('decisions.drawer.basisMetricsPlaceholder'), 'JSON 对象，如 {"pic50": 7.2}')
  })
})
