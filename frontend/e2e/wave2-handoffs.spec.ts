import { expect, test, type Page, type Route } from '@playwright/test'

const projectId = 'e2e-proj-1'
function envelope(data: unknown) { return { code: 200, message: 'success', data } }
async function json(route: Route, data: unknown) {
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope(data)) })
}
async function seedAuth(page: Page) {
  await page.context().addCookies([
    { name: 'cpumodel_access', value: 'e2e-access-token', domain: '127.0.0.1', path: '/' },
    { name: 'cpumodel_refresh', value: 'e2e-refresh-token', domain: '127.0.0.1', path: '/api/v1/auth' },
    { name: 'cpumodel_csrf', value: 'e2e-csrf-token', domain: '127.0.0.1', path: '/' },
  ])
}

test('ScreenResult hands off to ADMET with uploaded file_id and sends verified receptor provenance to MD', async ({ page }) => {
  await seedAuth(page)
  const uploadedPayloads: string[] = []
  await page.route('**/api/v1/**', async route => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (path.endsWith('/users/me')) await json(route, { id: 'u1', email: 'e2e@example.invalid', username: 'E2E', role: 'user', status: 'active' })
    else if (path.endsWith('/projects')) await json(route, { items: [{ id: projectId, name: 'Proj 1' }], total: 1 })
    else if (path.endsWith('/results/screen-1')) {
      await json(route, {
        id: 'screen-1', task_id: 'screen-1', project_id: projectId, status: 'success',
        outputs: [{ id: 'art-1', version_id: 'ver-1', standard_type: 'molecule_table@1', files: [{ role: 'summary_csv', download_url: '/api/v1/files/csv-1/download' }] }]
      })
    } else if (path.endsWith('/artifacts/art-1')) {
      await json(route, { id: 'art-1', latest_version: { id: 'ver-1', files: [{ role: 'summary_csv', download_url: '/api/v1/files/csv-1/download' }] } })
    } else if (path.endsWith('/artifacts/art-1/versions/ver-1/files/table_file/download')) {
      await route.fulfill({ status: 200, contentType: 'text/csv', body: 'rank,smiles,docking_score,passes\n1,CCO,-8.1,true\n2,bad smiles,-5.0,true\n' })
    } else if (path.endsWith('/tasks/screen-1')) {
      await json(route, {
        id: 'screen-1', project_id: projectId, status: 'success',
        input_snapshots: [{ inputRole: 'receptor_pdb', entityType: 'protein_structure', entityId: 'struct-9', fileId: 'file-rec-9', detail: { target_id: 'targ-9', protein_id: 'prot-9' } }]
      })
    } else if (path.endsWith('/files/upload') && req.method() === 'POST') {
      uploadedPayloads.push('uploaded')
      await json(route, { id: 'handoff-file-77', filename: 'screening-screen-1-admet.csv' })
    } else {
      await json(route, { items: [] })
    }
  })

  await page.goto('/tasks/screen-1/screening')
  await expect(page.getByTestId('screen-result-page')).toBeVisible()
  await page.getByTestId('screen-send-admet').click()
  await expect(page).toHaveURL(/\/predict\?.*file_id=handoff-file-77/)
  expect(uploadedPayloads.length).toBe(1)

  await page.goto('/tasks/screen-1/screening')
  await page.getByTestId('screen-send-md').click()
  await expect(page).toHaveURL(/\/md\?.*project_id=e2e-proj-1.*structure_id=struct-9/)
})

test('PropertyPredictResult sends filtered eligible molecules to Screening without __detail and saves candidate set', async ({ page }) => {
  await seedAuth(page)
  const createdCandidates: string[] = []
  let createdSetCount = 0
  await page.route('**/api/v1/**', async route => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (path.endsWith('/users/me')) await json(route, { id: 'u1', email: 'e2e@example.invalid', username: 'E2E', role: 'user', status: 'active' })
    else if (path.endsWith('/projects')) await json(route, { items: [{ id: projectId, name: 'Proj 1' }], total: 1 })
    else if (path.endsWith('/results/pred-1')) {
      await json(route, {
        id: 'pred-1', task_id: 'pred-1', project_id: projectId, status: 'success',
        outputs: [{ id: 'art-p1', version_id: 'ver-p1', standard_type: 'molecule_table@1', files: [{ role: 'summary_csv', download_url: '/api/v1/files/pcsv-1/download' }] }]
      })
    } else if (path.endsWith('/artifacts/art-p1')) {
      await json(route, { id: 'art-p1', latest_version: { id: 'ver-p1', files: [{ role: 'summary_csv', download_url: '/api/v1/files/pcsv-1/download' }] } })
    } else if (path.endsWith('/artifacts/art-p1/versions/ver-p1/files/table_file/download')) {
      await route.fulfill({ status: 200, contentType: 'text/csv', body: 'molecule_id,smiles,qed\nm1,CCO,0.85\nm2,CCN,0.20\n' })
    } else if (path.endsWith('/files/upload') && req.method() === 'POST') {
      await json(route, { id: 'handoff-pred-99', filename: 'prediction-pred-1-screening.csv' })
    } else if (path.endsWith(`/projects/${projectId}/candidates`) && req.method() === 'POST') {
      createdCandidates.push(req.postData() ?? '')
      await json(route, { id: `cand-${createdCandidates.length}` })
    } else if (path.endsWith(`/projects/${projectId}/candidate-sets`) && req.method() === 'POST') {
      createdSetCount += 1
      await json(route, { id: 'cset-55' })
    } else if (path.includes('/candidate-sets/cset-55/items') && req.method() === 'POST') {
      await json(route, { added: createdCandidates.length })
    } else {
      await json(route, { items: [] })
    }
  })

  await page.goto('/tasks/pred-1/predictions')
  await expect(page.getByTestId('predict-result-page')).toBeVisible()
  await page.getByTestId('predict-save-candidates').click()
  const modal = page.getByRole('dialog')
  await expect(modal).toBeVisible()
  await modal.getByRole('button', { name: /保\s*存|Save/i }).click()
  await expect.poll(() => createdSetCount).toBe(1)
  expect(createdCandidates.length).toBe(2)

  await page.getByTestId('predict-result-send-screening').click()
  await expect(page).toHaveURL(/\/screen\?.*file_id=handoff-pred-99/)
})
