import { expect, test, type Page, type Route } from '@playwright/test'

const projectId = 'e2e-project'

function response(data: unknown) {
  return { code: 200, message: 'success', data }
}

async function json(route: Route, data: unknown) {
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(response(data)) })
}

async function installMocks(page: Page, state: { uploadedFiles: number; submittedTask: Record<string, unknown> | null } = { uploadedFiles: 0, submittedTask: null }) {
  await page.context().addCookies([
    { name: 'cpumodel_access', value: 'e2e-access-token', domain: '127.0.0.1', path: '/' },
    { name: 'cpumodel_refresh', value: 'e2e-refresh-token', domain: '127.0.0.1', path: '/api/v1/auth' },
    { name: 'cpumodel_csrf', value: 'e2e-csrf-token', domain: '127.0.0.1', path: '/' },
  ])
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/users/me')) {
      await json(route, { id: 'e2e-user', email: 'e2e@example.invalid', username: 'E2E', role: 'user', status: 'active' })
    } else if (path.endsWith('/projects')) {
      await json(route, { items: [{ id: projectId, name: 'E2E Project' }, { id: 'proj-b', name: 'Project B' }], total: 2, page: 1, page_size: 100 })
    } else if (path.endsWith(`/projects/${projectId}/targets`)) {
      await json(route, { items: [{ id: 'targ-1', project_id: projectId, name: 'STAT6' }] })
    } else if (path.endsWith('/targets/targ-1')) {
      await json(route, { id: 'targ-1', project_id: projectId, name: 'STAT6', proteins: [{ id: 'prot-1', target_id: 'targ-1', name: 'STAT6 Human' }] })
    } else if (path.endsWith('/proteins/prot-1/structures')) {
      await json(route, { items: [{ id: 'struct-1', protein_id: 'prot-1', label: '1ABC PDB', structure_file_id: 'rec-file-1' }] })
    } else if (path.endsWith(`/projects/${projectId}/candidate-sets`)) {
      await json(route, { items: [], total: 0, page: 1, page_size: 100 })
    } else if (path.endsWith('/files/upload') && request.method() === 'POST') {
      state.uploadedFiles += 1
      await json(route, { id: 'uploaded-inline-1', filename: 'inline_smiles.csv' })
    } else if (path.endsWith('/tasks') && request.method() === 'POST') {
      state.submittedTask = request.postDataJSON() as Record<string, unknown>
      await json(route, { id: 'screen-task-1' })
    } else if (path.endsWith('/tools') || path.includes('/tools?')) {
      await json(route, {
        items: [
          { id: 'tool-vina', slug: 'autodock-vina-docking', name: 'Vina', category: 'docking', current_version_id: 'ver-vina', is_active: true, status: 'active' },
          { id: 'tool-vs', slug: 'virtual-screening', name: 'Virtual Screening', category: 'virtual_screening', current_version_id: 'ver-vs', is_active: true, status: 'active' },
        ],
        total: 2, page: 1, page_size: 100,
      })
    } else {
      await json(route, { items: [], total: 0, page: 1, page_size: 100 })
    }
  })
}

test('ADMET submit accepts inline SMILES, caps live previews at 12, and validates rows', async ({ page }) => {
  await installMocks(page)
  await page.goto(`/predict?project_id=${projectId}`)
  await page.getByTestId('predict-submit-source-smiles').click()
  const fourteenValid = Array.from({ length: 14 }, (_, i) => `${'C'.repeat(i + 1)}O`).join('\n')
  await page.getByTestId('predict-submit-smiles-input').fill(`${fourteenValid}\ninvalid smiles`)
  await expect(page.getByTestId('predict-submit-preview-count')).toContainText('14')
  await expect(page.getByTestId('predict-submit-preview-item')).toHaveCount(12)
  await expect(page.getByTestId('predict-submit-button')).toBeEnabled()
})

test('screening accepts valid inline SMILES, rejects empty library, and submits valid CSV payload', async ({ page }) => {
  const state = { uploadedFiles: 0, submittedTask: null as Record<string, unknown> | null }
  await installMocks(page, state)
  await page.goto(`/screen?project_id=${projectId}`)
  await page.getByTestId('screen-config-receptor-source').getByText(/从项目|project/i).click()
  await page.getByTestId('screen-config-target').locator('.ant-select-selector').click()
  await page.locator('.ant-select-item-option-content', { hasText: 'STAT6' }).click()
  await page.getByTestId('screen-config-protein').locator('.ant-select-selector').click()
  await page.locator('.ant-select-item-option-content', { hasText: 'STAT6 Human' }).click()
  await page.getByTestId('screen-config-structure').locator('.ant-select-selector').click()
  await page.locator('.ant-select-item-option-content', { hasText: 'struct-1' }).click()

  await page.getByTestId('screen-config-ligand-source').getByText(/手动|inline/i).click()
  await expect(page.getByTestId('screen-config-submit')).toBeDisabled()
  await page.getByTestId('screen-config-inline-smiles').fill('CCO\nnot smiles')
  await expect(page.getByTestId('screen-config-inline-preview').locator('code')).toHaveCount(1)
  await expect(page.getByTestId('screen-config-submit')).toBeEnabled()

  await page.getByTestId('screen-config-inline-smiles').fill('not smiles')
  await expect(page.getByTestId('screen-config-inline-preview').locator('code')).toHaveCount(0)
  await expect(page.getByTestId('screen-config-submit')).toBeDisabled()

  await page.getByTestId('screen-config-inline-smiles').fill('CCO\nCCN\ninvalid smiles')
  await page.getByTestId('screen-config-submit').click()
  await expect(page).toHaveURL(/\/tasks\/screen-task-1\/screening/)
  expect(state.uploadedFiles).toBe(1)
  expect((state.submittedTask?.standard_input_uploads as Record<string, string>)?.ligand_smiles).toBe('uploaded-inline-1')
})
