import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { test } from 'vitest'
import assert from 'node:assert/strict'

const rootDir = resolve(__dirname, '..')

function readProjectFile(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('frontend exposes a Playwright AIDD e2e test surface', () => {
  const packageJson = JSON.parse(readProjectFile('package.json'))
  const playwrightConfig = resolve(rootDir, 'playwright.config.ts')
  const researchFlowSpec = resolve(rootDir, 'e2e/aidd-research-flow.spec.ts')
  const boardPerformanceSpec = resolve(rootDir, 'e2e/research-board-performance.spec.ts')

  assert.equal(
    packageJson.scripts['test:e2e'],
    'bash ./scripts/install-playwright-deps.sh --ensure-runtime && playwright test',
  )
  assert.equal(packageJson.devDependencies['@playwright/test'].startsWith('^'), true)
  assert.equal(existsSync(playwrightConfig), true)
  assert.equal(existsSync(researchFlowSpec), true)
  assert.equal(existsSync(boardPerformanceSpec), true)
})

test('AIDD e2e specs cover the production critical user flows', () => {
  const researchFlow = readProjectFile('e2e/aidd-research-flow.spec.ts')
  const boardPerformance = readProjectFile('e2e/research-board-performance.spec.ts')

  for (const expectedText of [
    '创建项目',
    '创建会话',
    '上传黄金蛋白',
    '审批 LVpocket',
    '加入科研白板',
    '刷新后恢复',
  ]) {
    assert.equal(researchFlow.includes(expectedText), true, `missing ${expectedText}`)
  }

  assert.equal(boardPerformance.includes('200 个节点'), true)
  assert.equal(boardPerformance.includes('/projects/e2e-project/boards/e2e-board'), true)
})
