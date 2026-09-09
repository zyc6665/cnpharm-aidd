import { expect, test, type Page, type Route } from '@playwright/test'

const projectId = 'e2e-project'

function apiResponse(data: unknown) {
  return { code: 200, message: 'success', data }
}

async function fulfillJson(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(apiResponse(data)),
  })
}

async function installWorkflowMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('cpumodel_token', 'e2e-token')
    localStorage.setItem('cpumodel_refresh_token', 'e2e-refresh')
  })

  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname

    if (path.endsWith('/users/me')) {
      await fulfillJson(route, {
        id: 'e2e-user',
        email: 'e2e@example.com',
        username: 'E2E Owner',
        role: 'user',
        status: 'active',
      })
      return
    }

    if (path.endsWith(`/projects/${projectId}/artifacts`)) {
      await fulfillJson(route, { items: [] })
      return
    }

    if (path.endsWith('/workflows') || path.endsWith('/workflows/runs')) {
      await fulfillJson(route, { items: [], total: 0, page: 1, page_size: 100, total_pages: 0 })
      return
    }

    if (path.endsWith('/tools/workbench-groups')) {
      await fulfillJson(route, [])
      return
    }

    if (path.endsWith('/tools')) {
      await fulfillJson(route, { items: [], total: 0, page: 1, page_size: 100 })
      return
    }

    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })
}

test('AT-003 工作流页面可切换到 PubChem 到基础 ADMET 预设', async ({ page }) => {
  await installWorkflowMocks(page)

  await page.goto(`/projects/${projectId}/workflow`)
  await page.getByTestId('workflow-preset-select').click()
  await page.getByTitle('PubChem 到基础 ADMET').click()

  await expect(page.getByRole('heading', { name: 'PubChem 到基础 ADMET' })).toBeVisible()
  await expect(page.getByText('Fetch PubChem Ligand').first()).toBeVisible()
  await expect(page.getByText('RDKit Properties').first()).toBeVisible()
  await expect(page.getByText('MolP-PC 基础 ADMET').first()).toBeVisible()
  await expect(page.getByText('基础 ADMET 结果').first()).toBeVisible()
})
