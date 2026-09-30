import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'
import WorkspaceView from './index.vue'
import { getWorkspaceOverview } from '@/api/workspace'
import { listProjects } from '@/api/projects'
import { getSystemHealth } from '@/api/system'

vi.mock('@/api/workspace', () => ({ getWorkspaceOverview: vi.fn() }))
vi.mock('@/api/projects', () => ({ listProjects: vi.fn(), createProject: vi.fn() }))
vi.mock('@/api/system', () => ({ getSystemHealth: vi.fn() }))

const overview = {
  attention_task_count: 1,
  task_status_counts: { pending: 0, running: 1, success: 3, failure: 0, canceled: 0 },
  tasks: [{
    id: 'task-1',
    name: '分子对接任务',
    status: 'running',
    progress: 42,
    tool_id: 'tool-1',
    tool_name: 'Docking',
    tool_slug: 'docking',
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-30T00:01:00Z',
  }],
  workflows: [],
  files: [],
  frequent_tools: [{ id: 'tool-1', name: 'Docking', slug: 'docking', usage_count: 7 }],
}

const stubs = {
  RouterLink: { template: '<a><slot /></a>' },
  AButton: { template: '<button><slot /></button>' },
  AAlert: { template: '<div>{{ $attrs.message }}{{ $attrs.description }}<slot /><slot name="action" /></div>' },
  ASkeleton: true,
  AEmpty: true,
  AProgress: true,
  PlusOutlined: true,
  ExperimentOutlined: true,
  ApartmentOutlined: true,
  AppstoreOutlined: true,
  AModal: true,
}

function renderWorkspace() {
  return mount(WorkspaceView, {
    global: {
      plugins: [i18n],
      stubs,
      mocks: { $router: { push: vi.fn() } },
    },
  })
}

describe('WorkspaceView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getSystemHealth).mockResolvedValue({
      data: {
        status: 'healthy',
        version: '1.0.0',
        environment: 'test',
        timestamp: '2026-08-04T00:00:00Z',
        services: [],
      },
    } as never)
    vi.mocked(listProjects).mockResolvedValue({
      data: {
        items: [{
          id: 'project-1',
          organization_id: 'organization-1',
          created_by: 'user-1',
          name: '先导优化',
          goal: '筛选候选分子',
          status: 'active',
          model_policy: {},
          data_policy: {},
          membership: { id: 'membership-1', role: 'owner' },
          created_at: '2026-07-30T00:00:00Z',
          updated_at: '2026-07-30T00:00:00Z',
        }],
      },
    } as never)
  })

  it('展示最近项目和需要用户处理的失败任务，不展示旧仪表盘区块', async () => {
    vi.mocked(getWorkspaceOverview).mockResolvedValue({
      data: {
        ...overview,
        tasks: [{ ...overview.tasks[0], status: 'failure', error_message: '执行节点不可用' }],
      },
    } as never)
    const wrapper = renderWorkspace()
    await flushPromises()

    expect(listProjects).toHaveBeenCalledTimes(1)
    expect(getWorkspaceOverview).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('分子对接任务')
    expect(wrapper.text()).toContain('先导优化')
    expect(wrapper.text()).toContain('执行节点不可用')
    expect(wrapper.text()).not.toContain('常用工具')
    expect(wrapper.text()).not.toContain('使用 7 次')
  })

  it('概览接口失败时保留项目入口并展示可操作的降级提示', async () => {
    vi.mocked(getWorkspaceOverview).mockRejectedValue(new Error('network'))
    const wrapper = renderWorkspace()
    await flushPromises()

    expect(wrapper.text()).toContain('任务与 Artifact 暂时不可用')
    expect(wrapper.text()).toContain('先导优化')
    expect(wrapper.text()).not.toContain('研究工作台加载失败')
    expect(wrapper.findAll('button').some(button => button.text() === '重试')).toBe(true)
  })

  it('概览失败且 schema 健康检查异常时展示数据库迁移提示', async () => {
    vi.mocked(getWorkspaceOverview).mockRejectedValue(new Error('schema mismatch'))
    vi.mocked(getSystemHealth).mockResolvedValue({
      data: {
        status: 'unhealthy',
        version: '1.0.0',
        environment: 'test',
        timestamp: '2026-08-04T00:00:00Z',
        services: [{
          name: 'database_schema',
          status: 'unhealthy',
          message: 'Alembic revision mismatch: current=20260801_01, head=20260804_02',
        }],
      },
    } as never)

    const wrapper = renderWorkspace()
    await flushPromises()

    expect(getSystemHealth).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('数据库迁移未完成')
    expect(wrapper.text()).toContain('当前数据库结构落后于后端代码')
    expect(wrapper.text()).toContain('先导优化')
  })
})
