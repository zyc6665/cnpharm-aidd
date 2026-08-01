import { expect, test, type Page, type Route } from '@playwright/test'

const projectId = 'e2e-project'
const conversationId = 'e2e-conversation'
const boardId = 'e2e-board'
const runId = 'run-e2e'
const planId = 'plan-e2e'

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

async function installAiddMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('cpumodel_token', 'e2e-token')
    localStorage.setItem('cpumodel_refresh_token', 'e2e-refresh')
  })

  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()

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

    if (path.endsWith(`/projects/${projectId}`)) {
      await fulfillJson(route, {
        id: projectId,
        name: 'E2E 口袋研究',
        goal: '创建项目后识别可成药口袋',
        status: 'active',
        membership: { role: 'owner' },
      })
      return
    }

    if (path.endsWith(`/projects/${projectId}/conversations`) && method === 'GET') {
      await fulfillJson(route, {
        items: [{ id: conversationId, project_id: projectId, title: '创建会话', status: 'active' }],
      })
      return
    }

    if (path.endsWith(`/conversations/${conversationId}/messages`) && method === 'GET') {
      await fulfillJson(route, {
        items: [
          {
            id: 'message-goal',
            conversation_id: conversationId,
            branch_id: 'branch-e2e',
            role: 'user',
            content: [{ type: 'text', text: '上传黄金蛋白并识别口袋' }],
            plain_text: '上传黄金蛋白并识别口袋',
            sequence: 1,
          },
          {
            id: 'message-plan',
            conversation_id: conversationId,
            branch_id: 'branch-e2e',
            role: 'assistant',
            content: [
              { type: 'text', text: '已创建会话，并准备审批 LVpocket。' },
              {
                type: 'approval_ref',
                plan_id: planId,
                run_id: runId,
                tool: 'LVpocket',
                parameters: { receptor: 'golden-target.pdb' },
                resources: { accelerator: 'NVIDIA GPU', gpu_count: 1 },
                estimated_duration_seconds: 180,
                network_access: false,
                status: 'pending',
              },
            ],
            plain_text: '审批 LVpocket',
            sequence: 2,
          },
          {
            id: 'message-artifact',
            conversation_id: conversationId,
            branch_id: 'branch-e2e',
            role: 'assistant',
            content: [{ type: 'artifact_ref', title: '加入科研白板的 Pocket Artifact' }],
            plain_text: '加入科研白板',
            sequence: 3,
          },
        ],
      })
      return
    }

    if (path.endsWith(`/conversations/${conversationId}/messages`) && method === 'POST') {
      await fulfillJson(route, {
        id: 'message-new-goal',
        conversation_id: conversationId,
        branch_id: 'branch-e2e',
        role: 'user',
        content: [{ type: 'text', text: '上传黄金蛋白，审批 LVpocket 后加入科研白板' }],
        plain_text: '上传黄金蛋白，审批 LVpocket 后加入科研白板',
        sequence: 4,
      })
      return
    }

    if (path.endsWith(`/projects/${projectId}/conversations/${conversationId}/agent-runs`)) {
      await fulfillJson(route, {
        id: runId,
        project_id: projectId,
        conversation_id: conversationId,
        message: '上传黄金蛋白，审批 LVpocket 后加入科研白板',
        intent: 'pocket_exploration',
        status: 'planning',
        requested_outputs: ['pocket_result'],
        plan: {},
      })
      return
    }

    if (path.endsWith(`/plan-versions/${planId}/approve`)) {
      await fulfillJson(route, {
        id: planId,
        status: 'approved',
        execution: { execution_id: 'execution-e2e', state: 'queued' },
      })
      return
    }

    if (path.endsWith(`/agent-runs/${runId}/stream`)) {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body:
          'id: 1\n' +
          'event: execution_completed\n' +
          `data: ${JSON.stringify({
            run_id: runId,
            event_type: 'execution_completed',
            payload: { run_id: runId, summary: '刷新后恢复：LVpocket 已完成' },
          })}\n\n`,
      })
      return
    }

    if (path.endsWith('/research-boards') && method === 'GET') {
      await fulfillJson(route, {
        items: [{ id: boardId, project_id: projectId, name: 'Pocket 证据白板', node_count: 1 }],
        total: 1,
        page: 1,
        page_size: 100,
      })
      return
    }

    if (path.endsWith(`/research-boards/${boardId}`) && method === 'GET') {
      await fulfillJson(route, {
        id: boardId,
        project_id: projectId,
        owner_id: 'e2e-user',
        name: 'Pocket 证据白板',
        description: '加入科研白板',
        version: 1,
        content: {
          nodes: [
            { id: 'artifact-pocket', type: 'artifact', position: { x: 120, y: 120 }, artifact_id: 'artifact-pocket' },
          ],
          edges: [],
          viewport: { x: 0, y: 0, zoom: 1 },
        },
      })
      return
    }

    if (path.endsWith(`/projects/${projectId}/artifacts`)) {
      await fulfillJson(route, {
        items: [
          {
            id: 'artifact-pocket',
            project_id: projectId,
            artifact_type: 'pocket_result',
            semantic_type: 'pocket_result',
            name: 'lvpocket-result.json',
            description: '审批 LVpocket 后生成的口袋结果',
            latest_version: {
              id: 'artifact-pocket-v1',
              version: 1,
              filename: 'lvpocket-result.json',
              content_type: 'application/json',
              size_bytes: 256,
              sha256: 'b'.repeat(64),
              status: 'available',
              created_at: '2026-08-01T00:00:00Z',
            },
            created_at: '2026-08-01T00:00:00Z',
            updated_at: '2026-08-01T00:00:00Z',
          },
        ],
      })
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

test('创建项目到审批 LVpocket 再加入科研白板，刷新后恢复', async ({ page }) => {
  await installAiddMocks(page)

  await page.goto(`/projects/${projectId}/research/${conversationId}`)
  await expect(page.getByText('E2E 口袋研究')).toBeVisible()
  await expect(
    page.getByTestId('conversation-sidebar').getByRole('button', { name: /创建会话/ }),
  ).toBeVisible()
  await expect(page.getByText('上传黄金蛋白并识别口袋')).toBeVisible()
  await expect(page.getByText('审批 LVpocket')).toBeVisible()

  await page.getByPlaceholder('描述研究目标，或引用项目中的蛋白结构...').fill('上传黄金蛋白，审批 LVpocket 后加入科研白板')
  await page.getByTitle('发送').click()
  await page.getByTestId('approve-plan').click()
  await page.getByText('智能体过程').click()
  await expect(page.getByText('刷新后恢复：LVpocket 已完成')).toBeVisible()

  await page.goto(`/projects/${projectId}/boards/${boardId}`)
  await expect(page.getByTestId('research-board-page')).toBeVisible()
  await expect(page.getByText('Pocket 证据白板')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'lvpocket-result.json' })).toBeVisible()

  await page.reload()
  await expect(page.getByRole('heading', { name: 'lvpocket-result.json' })).toBeVisible()
})
