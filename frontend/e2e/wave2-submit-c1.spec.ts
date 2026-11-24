import { expect, test, type Page, type Route } from '@playwright/test'

function envelope(data: unknown) {
  return { code: 200, message: 'success', data }
}

async function json(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(envelope(data)),
  })
}

async function seedAuth(page: Page) {
  await page.context().addCookies([
    { name: 'cpumodel_access', value: 'e2e-access-token', domain: '127.0.0.1', path: '/' },
    { name: 'cpumodel_refresh', value: 'e2e-refresh-token', domain: '127.0.0.1', path: '/api/v1/auth' },
    { name: 'cpumodel_csrf', value: 'e2e-csrf-token', domain: '127.0.0.1', path: '/' },
  ])
}

test('MD deep-link prefill ignores stale responses on project switch and disables submit until valid structure', async ({ page }) => {
  await seedAuth(page)
  let resolveSlowTarget!: () => void
  const slowTargetGate = new Promise<void>(resolve => {
    resolveSlowTarget = resolve
  })

  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/users/me')) {
      await json(route, { id: 'u1', email: 'e2e@example.invalid', username: 'E2E', role: 'user', status: 'active' })
    } else if (path.endsWith('/projects')) {
      await json(route, {
        items: [
          { id: 'proj-a', name: 'Project A' },
          { id: 'proj-b', name: 'Project B' },
        ],
        total: 2,
      })
    } else if (path.endsWith('/tools') || path.includes('/tools')) {
      await json(route, {
        items: [{ id: 'tool-gromacs', slug: 'gromacs-md', name: 'GROMACS MD', category: 'simulation', is_active: true, status: 'active', parameter_schema: { type: 'object', properties: {} } }],
        total: 1,
      })
    } else if (path.endsWith('/structures/struct-a')) {
      await json(route, { id: 'struct-a', protein_id: 'prot-a', label: 'Struct A PDB', structure_file_id: 'file-a' })
    } else if (path.endsWith('/proteins/prot-a')) {
      await json(route, { id: 'prot-a', target_id: 'targ-a', name: 'Protein A' })
    } else if (path.endsWith('/targets/targ-a')) {
      await slowTargetGate
      await json(route, { id: 'targ-a', project_id: 'proj-a', name: 'Target A', proteins: [{ id: 'prot-a', target_id: 'targ-a', name: 'Protein A' }] })
    } else if (path.endsWith('/targets/targ-b')) {
      await json(route, { id: 'targ-b', project_id: 'proj-b', name: 'Target B', proteins: [{ id: 'prot-b', target_id: 'targ-b', name: 'Protein B' }] })
    } else if (path.endsWith('/projects/proj-a/targets')) {
      await json(route, { items: [{ id: 'targ-a', project_id: 'proj-a', name: 'Target A' }] })
    } else if (path.endsWith('/projects/proj-b/targets')) {
      await json(route, { items: [{ id: 'targ-b', project_id: 'proj-b', name: 'Target B' }] })
    } else if (path.endsWith('/targets/targ-b/proteins')) {
      await json(route, { items: [{ id: 'prot-b', target_id: 'targ-b', name: 'Protein B' }] })
    } else if (path.endsWith('/proteins/prot-b/structures')) {
      await json(route, { items: [{ id: 'struct-b', protein_id: 'prot-b', label: 'Struct B PDB', structure_file_id: 'file-b' }] })
    } else {
      await json(route, { items: [] })
    }
  })

  await page.goto('/md?project_id=proj-a&structure_id=struct-a')
  await expect(page.getByTestId('md-submit-page')).toBeVisible()
  const submitBtn = page.getByTestId('md-submit-btn')
  await expect(submitBtn).toBeDisabled()

  // Switch to Project B before Project A ancestry resolves
  await page.getByTestId('md-project-select').locator('.ant-select-selector').click()
  await page.locator('.ant-select-item-option-content', { hasText: 'Project B' }).click()
  resolveSlowTarget()

  // Project B target should appear, and Project A target must not leak back in
  await page.getByTestId('md-target-select').locator('.ant-select-selector').click()
  await expect(page.locator('.ant-select-item-option-content', { hasText: 'Target B' })).toBeVisible()
  await expect(page.locator('.ant-select-item-option-content', { hasText: 'Target A' })).toHaveCount(0)
  await expect(submitBtn).toBeDisabled()

  await page.locator('.ant-select-item-option-content', { hasText: 'Target B' }).click()
  await page.getByTestId('md-protein-select').locator('.ant-select-selector').click()
  await page.locator('.ant-select-item-option-content', { hasText: 'Protein B' }).click()
  await page.getByTestId('md-structure-select').locator('.ant-select-selector').click()
  await page.locator('.ant-select-item-option-content', { hasText: '#1' }).click()
  await expect(submitBtn).toBeEnabled()
})

test('design molecule generation renders offline with pocket cascade guards', async ({ page }) => {
  await seedAuth(page)
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/users/me')) {
      await json(route, { id: 'u1', email: 'e2e@example.invalid', username: 'E2E', role: 'user', status: 'active' })
    } else if (path.endsWith('/projects')) {
      await json(route, { items: [{ id: 'proj-a', name: 'Project A' }], total: 1 })
    } else if (path.includes('/tools')) {
      await json(route, { items: [], total: 0 })
    } else {
      await json(route, { items: [] })
    }
  })

  await page.goto('/design/molecules?project_id=proj-a')
  await expect(page.getByTestId('molecule-generation-page')).toBeVisible()
})
