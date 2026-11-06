import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { countPasses, funnelFromRankedRows } from '../src/views/screening/funnel'

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

test('tool slug 与冻结契约一致（molp-pc-property-prediction / autodock-vina-docking）', () => {
  const predictTypes = read('src/types/predict.ts')
  const screeningTypes = read('src/types/screening.ts')

  assert.ok(predictTypes.includes("'molp-pc-property-prediction'"), 'predict 侧缺少 molp-pc-property-prediction slug')
  assert.ok(
    screeningTypes.includes("'autodock-vina-docking'"),
    'screening 侧缺少 autodock-vina-docking slug'
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

test('筛选参数契约：Vina 1.1.0 七个真实参数与默认值', () => {
  const screeningTypes = read('src/types/screening.ts')
  for (const key of [
    'box_size',
    'exhaustiveness',
    'n_poses',
    'pharmacophore_min_features',
    'docking_score_cutoff',
    'top_n',
    'seed'
  ]) {
    assert.ok(screeningTypes.includes(`${key}:`), `ScreeningParams 缺少 ${key}`)
  }
  assert.ok(!screeningTypes.includes('device:'), 'Vina 1.1.0 不应暴露 device 参数')
})

test('漏斗真实统计：五层按 stage_pharmacophore/stage_docking/stage_cutoff/passes 计数', () => {
  const rows: Array<Record<string, string>> = [
    {
      stage_pharmacophore: 'true',
      stage_docking: 'true',
      stage_cutoff: 'true',
      passes: 'true'
    },
    {
      stage_pharmacophore: 'true',
      stage_docking: 'true',
      stage_cutoff: 'false',
      passes: 'false'
    },
    {
      stage_pharmacophore: 'true',
      stage_docking: 'false',
      stage_cutoff: 'false',
      passes: 'false'
    },
    {
      stage_pharmacophore: 'false',
      stage_docking: 'false',
      stage_cutoff: 'false',
      passes: 'false'
    }
  ]

  const stages = funnelFromRankedRows(rows)
  assert.deepEqual(
    stages.map(stage => stage.key),
    ['input', 'pharmacophore', 'docking', 'cutoff', 'kept']
  )
  assert.deepEqual(
    stages.map(stage => stage.remaining),
    [4, 3, 2, 1, 1]
  )
  assert.equal(countPasses(rows), 1)

  for (let i = 1; i < stages.length; i += 1) {
    assert.ok(
      stages[i].remaining <= stages[i - 1].remaining,
      `第 ${i} 层剩余数不应大于上一层`
    )
  }
})

test('漏斗真实统计：空表与全失败时各层归零', () => {
  assert.deepEqual(
    funnelFromRankedRows([]).map(stage => stage.remaining),
    [0, 0, 0, 0, 0]
  )

  const failed = [
    { stage_pharmacophore: 'false', stage_docking: 'false', stage_cutoff: 'false', passes: 'false' },
    { stage_pharmacophore: 'false', stage_docking: 'false', stage_cutoff: 'false', passes: 'false' }
  ]
  assert.deepEqual(
    funnelFromRankedRows(failed).map(stage => stage.remaining),
    [2, 0, 0, 0, 0]
  )
  assert.equal(countPasses(failed), 0)
})
