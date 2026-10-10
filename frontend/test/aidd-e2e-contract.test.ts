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
  const workflowPresetSpec = resolve(rootDir, 'e2e/at003-workflow-preset.spec.ts')

  assert.equal(
    packageJson.scripts['test:e2e'],
    'bash ./scripts/install-playwright-deps.sh --ensure-runtime && playwright test',
  )
  assert.equal(packageJson.devDependencies['@playwright/test'].startsWith('^'), true)
  assert.equal(existsSync(playwrightConfig), true)
  assert.equal(existsSync(researchFlowSpec), true)
  assert.equal(existsSync(workflowPresetSpec), true)
})

test('AIDD e2e specs cover the production critical user flows', () => {
  const researchFlow = readProjectFile('e2e/aidd-research-flow.spec.ts')
  const workflowPreset = readProjectFile('e2e/at003-workflow-preset.spec.ts')

  for (const expectedText of [
    '创建项目',
    '创建会话',
    '上传黄金蛋白',
    '审批 LVpocket',
    '刷新后恢复',
  ]) {
    assert.equal(researchFlow.includes(expectedText), true, `missing ${expectedText}`)
  }

  assert.equal(workflowPreset.includes('workflow-preset-select'), true)
  assert.equal(workflowPreset.includes('PubChem 到基础 ADMET'), true)
})
