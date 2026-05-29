import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('顶部导航应提供 CPUPDB 占位入口', () => {
  const layoutSource = readSource('src/components/layout/DefaultLayout.vue')

  assert.equal(layoutSource.includes("const cpupdbUrl = 'https://www.cpupdb.com'"), true)
  assert.equal(layoutSource.includes("t('nav.cpupdb')"), true)
})

test('首页第二屏应改为 AIDD 平台功能流程', () => {
  const homeSource = readSource('src/views/home/index.vue')
  const zhLocaleSource = readSource('src/locales/zh-CN/index.ts')
  const enLocaleSource = readSource('src/locales/en-US/index.ts')

  assert.equal(homeSource.includes('workflowSteps'), true)
  assert.equal(homeSource.includes('RightOutlined'), true)
  assert.equal(homeSource.includes("'moleculeGenerationOrVirtualScreening'"), true)
  assert.equal(homeSource.includes("'molecularDockingAndAffinityPrediction'"), true)

  const pocketIndex = homeSource.indexOf("'pocketExploration'")
  const generationIndex = homeSource.indexOf("'moleculeGenerationOrVirtualScreening'")
  const dockingIndex = homeSource.indexOf("'molecularDockingAndAffinityPrediction'")
  const propertyIndex = homeSource.indexOf("'propertyPrediction'")
  const leadIndex = homeSource.indexOf("'leadOptimization'")

  assert.equal(
    pocketIndex < generationIndex &&
      generationIndex < dockingIndex &&
      dockingIndex < propertyIndex &&
      propertyIndex < leadIndex,
    true
  )

  assert.equal(zhLocaleSource.includes("cpupdb: 'CPUPDB'"), true)
  assert.equal(zhLocaleSource.includes("title: '平台功能'"), true)
  assert.equal(zhLocaleSource.includes("title: '口袋探索'"), true)
  assert.equal(zhLocaleSource.includes("title: '分子生成或虚拟筛选'"), true)
  assert.equal(zhLocaleSource.includes("title: '分子对接及结合亲和力预测'"), true)
  assert.equal(zhLocaleSource.includes("title: '性质预测'"), true)
  assert.equal(zhLocaleSource.includes("title: '先导化合物优化'"), true)

  assert.equal(enLocaleSource.includes("cpupdb: 'CPUPDB'"), true)
  assert.equal(enLocaleSource.includes("title: 'Platform Functions'"), true)
  assert.equal(enLocaleSource.includes("title: 'Pocket Exploration'"), true)
  assert.equal(enLocaleSource.includes("title: 'Molecule Generation or Virtual Screening'"), true)
  assert.equal(
    enLocaleSource.includes("title: 'Molecular Docking and Binding Affinity Prediction'"),
    true
  )
  assert.equal(enLocaleSource.includes("title: 'Property Prediction'"), true)
  assert.equal(enLocaleSource.includes("title: 'Lead Optimization'"), true)
})
