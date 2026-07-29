import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('首页平台与页脚应提供 CPUPDB 入口', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('https://www.cpupdb.com'), true)
  assert.equal(homeSource.includes('<nav class="footer-nav">'), true)
})

test('首页第二屏应改为 AIDD 平台功能流程', () => {
  const homeSource = readSource('src/views/home/index.vue')
  const zhLocaleSource = readSource('src/locales/zh-CN/index.ts')
  const enLocaleSource = readSource('src/locales/en-US/index.ts')

  assert.equal(homeSource.includes('workflowSteps'), true)
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

test('首页首屏应提供产品工作台与分子视图预览', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('hero-container'), true)
  assert.equal(homeSource.includes('hero-preview'), true)
  assert.equal(homeSource.includes('preview-window'), true)
  assert.equal(homeSource.includes('preview-molecule'), true)
  assert.equal(homeSource.includes('mol-scaffold'), true)
})

test('首页应由首屏、价值、能力、平台与转化区组成', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('<section class="hero">'), true)
  assert.equal(homeSource.includes('<section class="values">'), true)
  assert.equal(homeSource.includes('<section class="capabilities">'), true)
  assert.equal(homeSource.includes('<section class="platform">'), true)
  assert.equal(homeSource.includes('<section class="cta">'), true)
})

test('首页预览应包含工作区导航和内容卡片层级', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('preview-sidebar'), true)
  assert.equal(homeSource.includes('preview-nav-item'), true)
  assert.equal(homeSource.includes('preview-content'), true)
  assert.equal(homeSource.includes('preview-card'), true)
})

test('首页平台区域应链接 PAIWSIT、CPUPDB 与注册入口', () => {
  const homeSource = readSource('src/views/home/index.vue')
  assert.equal(homeSource.includes("t('home.platform.title')"), true)
  assert.equal(homeSource.includes('http://www.paiwsit.com/'), true)
  assert.equal(homeSource.includes('https://www.cpupdb.com'), true)
  assert.equal(homeSource.includes('to="/register"'), true)
})

test('首页能力区应将流程步骤按连接关系呈现', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('capabilities-track'), true)
  assert.equal(homeSource.includes('cap-step'), true)
  assert.equal(homeSource.includes('cap-step-icon'), true)
  assert.equal(homeSource.includes('cap-connector'), true)
})

test('首页动画应支持减少动态效果偏好', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('prefers-reduced-motion: reduce'), true)
})

test('首页首屏和平台区应限制内容宽度', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('max-width: 640px;'), true)
  assert.equal(homeSource.includes('.platform-grid'), true)
})

test('首页页脚应提供产品导航', () => {
  const homeSource = readSource('src/views/home/index.vue')

  assert.equal(homeSource.includes('footer-brand'), true)
  assert.equal(homeSource.includes('footer-nav'), true)
  assert.equal(homeSource.includes('to="/workflow"'), true)
})
