import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'vitest'
import assert from 'node:assert/strict'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function read(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

/**
 * V3.0 每条需求的用例表业务规则都写着「预测与计算结果仅作为研发辅助参考，
 * 不作为实验验证结论」，而全站此前零命中（`docs/26` MOL-03-3 判为未实现）。
 * 这里锁住「所有展示预测/计算结果的页面都挂了免责说明」，新增结果页漏挂会红。
 */
const RESULT_VIEWS = [
  'src/views/results/ResultDetail.vue',
  'src/views/md/MdResult.vue',
  'src/views/md/FreeEnergyResult.vue',
  'src/views/predict/AffinityPredictDetail.vue',
  'src/views/predict/MoleculePredictDetail.vue',
  'src/views/predict/PropertyPredictResult.vue',
  'src/views/screening/DockingResultDetail.vue',
  'src/views/screening/ScreenResult.vue',
  'src/views/compounds/CandidateDetail.vue',
  'src/views/compounds/CompoundDetail.vue',
  'src/views/compounds/Compare.vue',
  'src/views/targets/StructureDetail.vue',
  'src/views/targets/Pockets.vue',
  'src/views/targets/PocketResidues.vue',
  'src/views/tasks/Result.vue',
  'src/views/tasks/GenericTaskResult.vue',
  'src/views/tasks/PocketTaskResult.vue',
  'src/views/tasks/StructureTaskResult.vue',
  'src/views/design/GenerationResults.vue',
  'src/views/workflow/RunDetail.vue'
]

test('结果类页面统一挂载免责说明组件', () => {
  for (const view of RESULT_VIEWS) {
    const source = read(view)
    assert.ok(
      source.includes("import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'"),
      `${view} 未引入 ResultDisclaimer`
    )
    assert.ok(source.includes('<ResultDisclaimer />'), `${view} 未使用 ResultDisclaimer`)
  }
})

test('免责说明中英文文案与 V3.0 业务规则一致', () => {
  const zh = read('src/locales/zh-CN/index.ts')
  const en = read('src/locales/en-US/index.ts')
  assert.ok(
    zh.includes('预测与计算结果仅作为研发辅助参考，不作为实验验证结论'),
    'zh-CN 缺少免责说明文案'
  )
  assert.ok(
    en.includes('must not be treated as experimental conclusions'),
    'en-US 缺少免责说明文案'
  )
})

test('免责说明组件可被测试定位', () => {
  const component = read('src/components/common/ResultDisclaimer.vue')
  assert.ok(component.includes("data-testid=\"result-disclaimer\""))
  assert.ok(component.includes("t('common.disclaimer.resultNotice')"))
})
