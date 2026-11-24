import { expect, test, type Page, type Route } from '@playwright/test'

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

const sampleSdf = [
  'pose_1\n  RDKit\n\n  1  0  0  0  0  0  0  0  0999 V2000\n    1.0000    0.0000    0.0000 C   0  0\nM  END\n$$$$\n',
  'pose_3\n  RDKit\n\n  1  0  0  0  0  0  0  0  0999 V2000\n    2.0000    0.0000    0.0000 N   0  0\nM  END\n$$$$\n',
  'pose_5\n  RDKit\n\n  1  0  0  0  0  0  0  0  0999 V2000\n    3.0000    0.0000    0.0000 O   0  0\nM  END\n$$$$\n',
].join('')

const samplePdb = [
  'ATOM      1  CA  MET A 769      10.000  10.000  10.000  1.00 20.00           C',
  'END',
].join('\n')

test('docking detail steps non-first poses with zero extra API requests and exposes viewer controls', async ({ page }) => {
  await seedAuth(page)
  let apiCallsAfterInitial = 0
  let initialLoaded = false

  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (initialLoaded) apiCallsAfterInitial += 1
    if (path.endsWith('/users/me')) await json(route, { id: 'u1', email: 'e2e@example.invalid', username: 'E2E', role: 'user', status: 'active' })
    else if (path.endsWith('/results/dock-1')) {
      await json(route, {
        id: 'dock-1', task_id: 'dock-1', status: 'success',
        outputs: [{ id: 'art-d1', version_id: 'ver-d1', standard_type: 'ligand_structure@1' }],
      })
    } else if (path.endsWith('/metadata_json/download')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          poses: [
            { pose_id: 'pose_1', rank: 1, docking_score: -9.2, rmsd_lb: 0.0, rmsd_ub: 0.0, interactions: [] },
            { pose_id: 'pose_3', rank: 3, docking_score: -8.1, rmsd_lb: 1.1, rmsd_ub: 2.0, interactions: [{ type: 'hydrogen_bond', residue: 'MET769', chain: 'A', distance: 2.8 }] },
            { pose_id: 'pose_5', rank: 5, docking_score: -7.0, rmsd_lb: 2.1, rmsd_ub: 3.1, interactions: [] },
          ],
        }),
      })
    } else if (path.endsWith('/structure_3d_sdf/download')) {
      await route.fulfill({ status: 200, contentType: 'chemical/x-mdl-sdfile', body: sampleSdf })
    } else if (path.endsWith('/tasks/dock-1')) {
      await json(route, {
        id: 'dock-1', status: 'success',
        input_files: [{ relative_path: 'protein.pdb', filename: 'protein.pdb', url: '/api/v1/files/rec-1/download' }],
      })
    } else if (path.endsWith('/files/rec-1/download')) {
      await route.fulfill({ status: 200, contentType: 'chemical/x-pdb', body: samplePdb })
    } else {
      await json(route, { items: [] })
    }
  })

  await page.goto('/docking-results/pose-3?task_id=dock-1')
  await expect(page.getByTestId('docking-detail-score')).toContainText('pose_3')
  await expect(page.getByTestId('docking-interaction-residue')).toHaveText('MET769')
  await expect(page.getByTestId('viewer-spin-toggle')).toBeVisible()
  await expect(page.getByTestId('viewer-layer-receptor')).toBeVisible()
  await expect(page.getByTestId('viewer-layer-ligand')).toBeVisible()
  await expect(page.getByTestId('viewer-nearby-residues')).toBeVisible()

  initialLoaded = true
  await page.getByTestId('docking-detail-next').click()
  await expect(page.getByTestId('docking-detail-score')).toContainText('pose_5')
  await page.getByTestId('docking-detail-previous').click()
  await expect(page.getByTestId('docking-detail-score')).toContainText('pose_3')
  await page.goBack()
  await expect(page.getByTestId('docking-detail-score')).toContainText('pose_5')
  expect(apiCallsAfterInitial).toBe(0)

  await page.getByTestId('viewer-spin-toggle').click()
  await expect(page.getByTestId('viewer-spin-toggle')).toHaveAttribute('aria-pressed', 'true')
  await page.getByTestId('viewer-layer-ligand').click()
  await expect(page.getByTestId('viewer-layer-ligand')).toHaveAttribute('aria-pressed', 'false')
})

test('docking detail handles ligand-only result and unavailable record cleanly', async ({ page }) => {
  await seedAuth(page)
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/users/me')) await json(route, { id: 'u1', email: 'e2e@example.invalid', username: 'E2E', role: 'user', status: 'active' })
    else if (path.endsWith('/results/dock-2')) {
      await json(route, { id: 'dock-2', task_id: 'dock-2', status: 'success', outputs: [{ id: 'art-d2', version_id: 'ver-d2', standard_type: 'ligand_structure@1' }] })
    } else if (path.endsWith('/metadata_json/download')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          poses: [
            { pose_id: 'pose_a', rank: 1, docking_score: -8.0, rmsd_lb: 0, rmsd_ub: 0, interactions: [] },
            { pose_id: 'pose_unmapped', rank: 2, docking_score: -7.0, rmsd_lb: 0, rmsd_ub: 0, interactions: [] },
          ],
        }),
      })
    } else if (path.endsWith('/structure_3d_sdf/download')) {
      await route.fulfill({ status: 200, contentType: 'chemical/x-mdl-sdfile', body: 'pose_a\n  RDKit\n\n  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n$$$$\n' })
    } else if (path.endsWith('/tasks/dock-2')) {
      await json(route, { id: 'dock-2', status: 'success', input_files: [] })
    } else {
      await json(route, { items: [] })
    }
  })

  await page.goto('/docking-results/pose_unmapped?task_id=dock-2')
  await expect(page.getByTestId('docking-detail-receptor-warning')).toBeVisible()
  await expect(page.getByTestId('docking-detail-unavailable')).toBeVisible()
})
