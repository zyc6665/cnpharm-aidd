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
  assert.equal(layoutSource.includes("key: 'cpupdb', labelKey: 'nav.cpupdb', href: cpupdbUrl"), true)
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

test('首页首屏应提供产品化工作台视觉预览', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('hero-shell'), true)
  assert.equal(homeSource.includes('hero-copy'), true)
  assert.equal(homeSource.includes('hero-preview'), true)
  assert.equal(homeSource.includes('preview-pipeline'), true)
  assert.equal(homeSource.includes('preview-structure'), true)
  assert.equal(homeSource.includes('preview-metrics'), true)
})

test('首页平台特性区应改为 CPUModel 与 CPUPDB 的双栏叙事介绍区', () => {
  const homeSource = readSource('src/views/home/index.vue')
  const zhLocaleSource = readSource('src/locales/zh-CN/index.ts')
  const enLocaleSource = readSource('src/locales/en-US/index.ts')

  assert.equal(homeSource.includes('foundation-section'), true)
  assert.equal(homeSource.includes("t('home.foundation.title')"), true)
  assert.equal(homeSource.includes("t('home.foundation.platform.title')"), true)
  assert.equal(homeSource.includes("t('home.foundation.cpupdb.title')"), true)
  assert.equal(homeSource.includes('https://www.cpupdb.com'), true)
  assert.equal(homeSource.includes('https://www.cpupdb.com/help.html'), true)
  assert.equal(homeSource.includes("t('home.features.title')"), false)
  assert.equal(homeSource.includes('const features = {'), false)

  assert.equal(zhLocaleSource.includes("foundation: {"), true)
  assert.equal(zhLocaleSource.includes("title: '平台模型与数据底座'"), true)
  assert.equal(zhLocaleSource.includes("title: 'CPUModel 工作台'"), true)
  assert.equal(zhLocaleSource.includes("title: 'CPUPDB'"), true)

  assert.equal(enLocaleSource.includes("foundation: {"), true)
  assert.equal(enLocaleSource.includes("title: 'Platform Model & Data Foundation'"), true)
  assert.equal(enLocaleSource.includes("title: 'CPUModel Workbench'"), true)
  assert.equal(enLocaleSource.includes("title: 'CPUPDB'"), true)
})

test('首页平台功能区应升级为与下方大甲板同系的流程甲板', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('workflow-shell'), true)
  assert.equal(homeSource.includes('workflow-bridge'), true)
  assert.equal(homeSource.includes('workflow-track'), true)
  assert.equal(homeSource.includes('workflow-connector'), true)
  assert.equal(homeSource.includes('workflow-step-card'), true)
  assert.equal(homeSource.includes('workflow-step-kicker'), true)
  assert.equal(homeSource.includes('workflow-step-glow'), true)
  assert.equal(homeSource.includes('workflow-step-copy'), true)
})

test('首页中段甲板应具备滚动进入动效与渐进显隐状态', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('IntersectionObserver'), true)
  assert.equal(homeSource.includes('workflowRevealRef'), true)
  assert.equal(homeSource.includes('foundationRevealRef'), true)
  assert.equal(homeSource.includes('section-visible'), true)
  assert.equal(homeSource.includes('--reveal-delay'), true)
  assert.equal(homeSource.includes('prefers-reduced-motion: reduce'), true)
})

test('首页两个中段甲板应使用相同的外层宽度约束', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(
    homeSource.includes('.scenarios-section .container,\n  .foundation-section .container'),
    true
  )
  assert.equal(homeSource.includes('max-width: 1480px;'), true)
})

test('首页两个中段甲板应共享同一套上下留白节奏', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('--deck-stack-gap'), true)
  assert.equal(homeSource.includes('padding: @spacing-xxl 0 var(--deck-stack-gap);'), true)
  assert.equal(homeSource.includes('padding: var(--deck-stack-gap) 0 @spacing-xxl;'), true)
})
