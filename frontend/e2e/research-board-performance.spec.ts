import { expect, test, type Page, type Route } from '@playwright/test'

const projectId = 'e2e-project'
const boardId = 'e2e-board'

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

async function installBoardMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('cpumodel_token', 'e2e-token')
    localStorage.setItem('cpumodel_refresh_token', 'e2e-refresh')
  })

  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const nodes = Array.from({ length: 200 }, (_, index) => ({
      id: `note-${index}`,
      type: 'note',
      position: { x: 40 + (index % 20) * 76, y: 40 + Math.floor(index / 20) * 88 },
      content: `200 个节点性能样例 ${index + 1}`,
    }))

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

    if (path.endsWith(`/research-boards/${boardId}`)) {
      await fulfillJson(route, {
        id: boardId,
        project_id: projectId,
        owner_id: 'e2e-user',
        name: '200 个节点性能白板',
        description: '白板 200 节点仍可缩放、平移和选择',
        version: 1,
        content: { nodes, edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
      })
      return
    }

    if (path.endsWith(`/projects/${projectId}/artifacts`)) {
      await fulfillJson(route, { items: [] })
      return
    }

    if (path.endsWith('/files')) {
      await fulfillJson(route, { items: [], total: 0, page: 1, page_size: 100 })
      return
    }

    if (path.endsWith('/tools')) {
      await fulfillJson(route, { items: [], total: 0, page: 1, page_size: 100 })
      return
    }

    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })
}

test('项目白板 200 个节点仍可缩放、平移和选择', async ({ page }) => {
  await installBoardMocks(page)

  await page.goto('/projects/e2e-project/boards/e2e-board')
  const stage = page.getByTestId('board-stage')
  await expect(stage).toHaveAttribute('data-node-count', '200')
  await expect(stage).toHaveAttribute('aria-label', '科研白板画布，当前 200 个节点')

  const beforeZoom = await stage.boundingBox()
  await page.getByTitle('放大').click()
  const afterZoom = await stage.boundingBox()
  expect(afterZoom?.width || 0).toBeGreaterThan(beforeZoom?.width || 0)

  await page.mouse.move(620, 360)
  await page.mouse.down()
  await page.mouse.move(520, 300)
  await page.mouse.up()
  await page.locator('.board-node').first().click()
  await expect(page.getByText('当前选中')).toBeVisible()
})
