import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(__dirname, '..')

function read(path: string): string {
  return readFileSync(resolve(root, path), 'utf-8')
}

test('提交类页面不得无条件展示 mock 告警条', () => {
  for (const path of [
    'src/views/predict/PropertyPredictSubmit.vue',
    'src/views/screening/ScreenConfig.vue'
  ]) {
    const source = read(path)
    // 旧实现是一条永远渲染的 a-alert，文案写死「本结果由 mock 模型包生成」；
    // 真实模型包上线后它就变成事实错误，所以这里守住「必须数据驱动」。
    assert.ok(!source.includes('predict.banner.disclaimer'), `${path} 仍引用结果页 mock 文案`)
    assert.ok(!source.includes('screening.banner.disclaimer'), `${path} 仍引用结果页 mock 文案`)
    assert.ok(source.includes('useToolMockBanner'), `${path} 未使用工具级 mock 标记`)
    assert.ok(source.includes('MockDataBanner'), `${path} 未使用统一的横幅组件`)
  }
})

test('mock 标记来自后端工具包清单，不来自页面常量', () => {
  const composable = read('src/composables/useToolMockBanner.ts')
  assert.ok(composable.includes('getToolList'))
  assert.ok(composable.includes('matched?.mock === true'))
  const types = read('src/types/models.d.ts')
  assert.ok(types.includes('mock?: boolean'))
})

test('MockDataBanner 默认为不展示', () => {
  const banner = read('src/components/common/MockDataBanner.vue')
  assert.ok(banner.includes('mock: false'))
})
