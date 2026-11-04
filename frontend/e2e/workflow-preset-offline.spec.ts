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
  // 认证已改为 httpOnly Cookie（cpumodel_access/cpumodel_refresh）+ 可读 CSRF Cookie，
  // 不能再只写 localStorage。这里预置 Cookie，模拟已登录会话。
  await page.context().addCookies([
    { name: 'cpumodel_access', value: 'e2e-access-token', domain: '127.0.0.1', path: '/' },
    { name: 'cpumodel_refresh', value: 'e2e-refresh-token', domain: '127.0.0.1', path: '/api/v1/auth' },
    { name: 'cpumodel_csrf', value: 'e2e-csrf-token', domain: '127.0.0.1', path: '/' },
  ])

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

test('工作流页面可切换到配体结构到基础 ADMET 预设', async ({ page }) => {
  await installWorkflowMocks(page)

  await page.goto(`/projects/${projectId}/workflow`)
  // 工作流页默认进入「引导式」页签；预设选择位于「手动模式」页签下。
  await page.getByRole('tab', { name: '手动模式' }).click()
  await page.getByTestId('workflow-preset-select').click()
  await page.getByTitle('配体结构到基础 ADMET').click()

  await expect(page.getByRole('heading', { name: '配体结构到基础 ADMET' })).toBeVisible()
  await expect(page.getByText('配体结构输入').first()).toBeVisible()
  await expect(page.getByText('RDKit Properties').first()).toBeVisible()
  await expect(page.getByText('MolP-PC 基础 ADMET').first()).toBeVisible()
  await expect(page.getByText('基础 ADMET 结果').first()).toBeVisible()
})

test('工作流预设不再包含联网抓取配体的流程', async ({ page }) => {
  await installWorkflowMocks(page)

  await page.goto(`/projects/${projectId}/workflow`)
  await page.getByRole('tab', { name: '手动模式' }).click()
  await page.getByTestId('workflow-preset-select').click()

  await expect(page.getByTitle('PubChem 到基础 ADMET')).toHaveCount(0)
})
