import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  countPasses,
  dockingPassRate,
  estimateFunnel,
  funnelFromRankedRows,
  pharmacophorePassRate
} from '../src/views/screening/funnel'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const read = (rel: string): string => readFileSync(resolve(root, rel), 'utf8')

test('五条路由：P-21..P-25 都在 router 中以正确 path/name/组件注册', () => {
  const router = read('src/router/index.ts')

  const expected = [
    { path: '/predict', name: 'PropertyPredict', component: 'views/predict/PropertyPredictSubmit.vue' },
    { path: '/tasks/:id/predictions', name: 'PropertyPredictResult', component: 'views/predict/PropertyPredictResult.vue' },
    { path: '/screen', name: 'ScreenConfig', component: 'views/screening/ScreenConfig.vue' },
    { path: '/tasks/:id/screening', name: 'ScreenResult', component: 'views/screening/ScreenResult.vue' },
    { path: '/docking-results/:id', name: 'DockingResultDetail', component: 'views/screening/DockingResultDetail.vue' }
  ]

  for (const route of expected) {
    assert.ok(router.includes(`path: '${route.path}'`), `缺少路由 path: ${route.path}`)
    assert.ok(router.includes(`name: '${route.name}'`), `缺少路由 name: ${route.name}`)
    assert.ok(router.includes(route.component), `缺少路由组件: ${route.component}`)
    assert.ok(
      existsSync(resolve(root, 'src', route.component)),
      `路由组件文件不存在: ${route.component}`
    )
  }
})

test('tool slug 与冻结契约一致（admet-prediction / vina-virtual-screening）', () => {
  const predictTypes = read('src/types/predict.ts')
  const screeningTypes = read('src/types/screening.ts')

  assert.ok(predictTypes.includes("'admet-prediction'"), 'predict 侧缺少 admet-prediction slug')
  assert.ok(
    screeningTypes.includes("'vina-virtual-screening'"),
    'screening 侧缺少 vina-virtual-screening slug'
  )
  // 8 个 task_groups 必须与契约完全一致
  const groups = [
    'Absorption',
    'Distribution',
    'Excretion',
    'Metabolism',
    'Toxicology',
    'Tox21',
    'Ecotoxicity',
    'LD50'
  ]
  for (const group of groups) {
    assert.ok(predictTypes.includes(`'${group}'`), `PREDICT_TASK_GROUPS 缺少 ${group}`)
  }
})

test('漏斗预估：输入配体数与阈值真实参与，每层剩余数计算正确', () => {
  // 默认阈值：药效团 3 特征→70%；对接 -8 kcal/mol→50%；exhaustiveness 8→0.94
  // 1000 → 700 → round(700 * 0.47)=329 → min(329, topN=50)=50
  const stages = estimateFunnel({
    ligandCount: 1000,
    pharmacophoreMinFeatures: 3,
    dockingScoreCutoff: -8,
    exhaustiveness: 8,
    topN: 50
  })

  assert.deepEqual(
    stages.map(stage => stage.key),
    ['input', 'pharmacophore', 'docking', 'rescore']
  )
  assert.deepEqual(
    stages.map(stage => stage.remaining),
    [1000, 700, 329, 50]
  )

  // 剩余数量必须单调不增
  for (let i = 1; i < stages.length; i += 1) {
    assert.ok(
      stages[i].remaining <= stages[i - 1].remaining,
      `第 ${i} 层剩余数不应大于上一层`
    )
  }
})

test('漏斗预估：更严格的阈值产出更少的剩余（不是写死）', () => {
  const loose = estimateFunnel({
    ligandCount: 1000,
    pharmacophoreMinFeatures: 2,
    dockingScoreCutoff: -4,
    exhaustiveness: 16,
    topN: 1000
  })
  const strict = estimateFunnel({
    ligandCount: 1000,
    pharmacophoreMinFeatures: 5,
    dockingScoreCutoff: -12,
    exhaustiveness: 1,
    topN: 1000
  })

  assert.ok(loose[1].remaining > strict[1].remaining, '药效团更严格应剩余更少')
  assert.ok(loose[2].remaining > strict[2].remaining, '对接更严格应剩余更少')
  assert.ok(loose[3].remaining > strict[3].remaining, '整体更严格应剩余更少')
})

test('漏斗预估：top_n 限制最终剩余，输入非法时归零', () => {
  const limited = estimateFunnel({
    ligandCount: 100,
    pharmacophoreMinFeatures: 1,
    dockingScoreCutoff: 0,
    exhaustiveness: 30,
    topN: 10
  })
  assert.equal(limited[3].remaining, 10)

  const zero = estimateFunnel({
    ligandCount: 0,
    pharmacophoreMinFeatures: 3,
    dockingScoreCutoff: -8,
    exhaustiveness: 8,
    topN: 50
  })
  assert.deepEqual(
    zero.map(stage => stage.remaining),
    [0, 0, 0, 0]
  )
})

test('通过率函数：默认参数与契约预估一致', () => {
  assert.ok(Math.abs(pharmacophorePassRate(3) - 0.7) < 1e-9)
  assert.ok(Math.abs(dockingPassRate(-8) - 0.5) < 1e-9)
})

test('漏斗真实统计：按 stage_pharmacophore/stage_docking/stage_rescore 逐层计数', () => {
  const rows: Array<Record<string, string>> = [
    { stage_pharmacophore: 'true', stage_docking: 'true', stage_rescore: 'true', passes: 'true' },
    { stage_pharmacophore: 'true', stage_docking: 'true', stage_rescore: 'false', passes: 'false' },
    { stage_pharmacophore: 'true', stage_docking: 'false', stage_rescore: 'false', passes: 'false' },
    { stage_pharmacophore: 'false', stage_docking: 'false', stage_rescore: 'false', passes: 'false' }
  ]

  const stages = funnelFromRankedRows(rows)
  assert.deepEqual(
    stages.map(stage => stage.remaining),
    [4, 3, 2, 1]
  )
  assert.equal(countPasses(rows), 1)
})
