import { mkdirSync } from 'node:fs'
import { expect, test } from '@playwright/test'

const SHOT_DIR = '/tmp/shots-preview'
mkdirSync(SHOT_DIR, { recursive: true })

const ADMIN_USER = 'admin'
const ADMIN_PASS = process.env.ADMIN_PASSWORD || 'admin123'

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  const inputs = page.locator('input')
  await inputs.nth(0).fill(ADMIN_USER)
  await inputs.nth(1).fill(ADMIN_PASS)
  await page.locator('button[type="submit"]').click()
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 30000 })
}

async function openRow(page: import('@playwright/test').Page, needle: string) {
  const row = page.locator('[data-testid="recent-artifact-row"]').filter({ hasText: needle }).first()
  await expect(row).toBeVisible({ timeout: 30000 })
  return row
}

async function closeDrawer(page: import('@playwright/test').Page) {
  const closeBtn = page.locator('.ant-drawer-close')
  if (await closeBtn.isVisible().catch(() => false)) {
    await closeBtn.click()
  } else {
    await page.keyboard.press('Escape')
  }
  await expect(page.locator('[data-testid="artifact-preview-drawer"]')).toBeHidden({ timeout: 10000 })
}

test.describe('工作台最近 Artifact：先预览再下载', () => {
  test('点击行不直接下载，预览抽屉展示内容，下载按钮才触发下载', async ({ page }) => {
    const downloads: string[] = []
    page.on('download', download => downloads.push(download.suggestedFilename()))

    await login(page)
    await page.goto('/workspace')
    await expect(page.locator('[data-testid="recent-artifact-row"]').first()).toBeVisible({ timeout: 30000 })

    // 任务二：截图里的机器名标题已退化为「类型中文名 · vN」，原始串不再当标题。
    const smilesRow = page.locator('[data-testid="recent-artifact-row"]').filter({ hasText: 'molp_smoke.csv' }).first()
    await expect(smilesRow).toContainText('分子表')
    await expect(smilesRow).not.toContainText('smiles_csv')
    const machinePdbRow = page.locator('[data-testid="recent-artifact-row"]').filter({ hasText: 'msign_complex.pdb' }).first()
    await expect(machinePdbRow).toContainText('蛋白结构')
    await expect(machinePdbRow).not.toContainText('protein_pdb')
    await page.locator('.artifact-list').screenshot({ path: `${SHOT_DIR}/00-artifact-list.png` })

    // ① CSV 产物：点击行应打开预览抽屉（无下载、无导航）
    const csvRow = await openRow(page, 'cb_data_result.csv')
    const urlBefore = page.url()
    await csvRow.click()

    const drawer = page.locator('[data-testid="artifact-preview-drawer"]')
    await expect(drawer).toBeVisible({ timeout: 15000 })
    await expect(page.locator('[data-testid="artifact-preview-csv"]')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('[data-testid="artifact-preview-csv"] .ant-table-tbody tr:not(.ant-table-measure-row)').first()).toBeVisible({ timeout: 15000 })
    expect(page.url()).toBe(urlBefore)
    expect(downloads).toHaveLength(0)
    await page.screenshot({ path: `${SHOT_DIR}/01-csv-preview.png`, fullPage: true })

    // ③ 抽屉内下载按钮点击后才真正下载
    const downloadPromise = page.waitForEvent('download')
    await page.locator('[data-testid="artifact-preview-download"]').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toContain('cb_data_result.csv')
    expect(downloads.length).toBeGreaterThan(0)
    await closeDrawer(page)

    // ② JSON 产物：结构化预览
    const jsonRow = await openRow(page, 'report.json')
    await jsonRow.click()
    await expect(page.locator('[data-testid="artifact-preview-drawer"]')).toBeVisible({ timeout: 15000 })
    const jsonBody = page.locator('[data-testid="artifact-preview-file"]')
    await expect(jsonBody).toBeVisible({ timeout: 15000 })
    await expect(jsonBody).toContainText('predicted_rows', { timeout: 20000 })
    expect(page.url()).toBe(urlBefore)
    await page.screenshot({ path: `${SHOT_DIR}/02-json-preview.png`, fullPage: true })
    await closeDrawer(page)

    // ② PDB 结构产物：三维/结构预览
    const pdbRow = await openRow(page, 'structure.pdb')
    await pdbRow.click()
    const structure = page.locator('[data-testid="artifact-preview-structure"]')
    await expect(structure).toBeVisible({ timeout: 15000 })
    await expect(structure).not.toBeEmpty({ timeout: 30000 })
    await expect(structure.locator('canvas').first()).toBeVisible({ timeout: 30000 })
    await page.waitForTimeout(3000)
    await page.screenshot({ path: `${SHOT_DIR}/03-pdb-preview.png`, fullPage: true })
    expect(page.url()).toBe(urlBefore)
    await closeDrawer(page)

    // 全程只有抽屉内下载按钮触发过下载
    expect(downloads).toHaveLength(1)
  })
})
