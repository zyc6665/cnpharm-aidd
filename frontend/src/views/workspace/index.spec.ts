import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'
import WorkspaceView from './index.vue'
import { getWorkspaceOverview } from '@/api/workspace'

vi.mock('@/api/workspace', () => ({ getWorkspaceOverview: vi.fn() }))
vi.mock('@/api/tasks', () => ({ cancelTask: vi.fn(), retryTask: vi.fn() }))

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
  boards: [{ id: 'board-1', name: '先导优化', node_count: 4, updated_at: '2026-07-30T00:00:00Z' }],
  workflows: [],
  files: [],
  frequent_tools: [{ id: 'tool-1', name: 'Docking', slug: 'docking', usage_count: 7 }],
}

const stubs = {
  RouterLink: { template: '<a><slot /></a>' },
  AButton: { template: '<button><slot /></button>' },
  AAlert: { template: '<div>{{ $attrs.message }}<slot /><slot name="action" /></div>' },
  ASkeleton: true,
  AEmpty: true,
  AProgress: true,
  PlusOutlined: true,
  ExperimentOutlined: true,
  ApartmentOutlined: true,
  AppstoreOutlined: true,
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
  beforeEach(() => vi.clearAllMocks())

  it('通过单一聚合接口展示任务、白板和常用工具', async () => {
    vi.mocked(getWorkspaceOverview).mockResolvedValue({ data: overview } as never)
    const wrapper = renderWorkspace()
    await flushPromises()

    expect(getWorkspaceOverview).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('分子对接任务')
    expect(wrapper.text()).toContain('先导优化')
    expect(wrapper.text()).toContain('使用 7 次')
  })

  it('接口失败时展示可操作的重试状态', async () => {
    vi.mocked(getWorkspaceOverview).mockRejectedValue(new Error('network'))
    const wrapper = renderWorkspace()
    await flushPromises()

    expect(wrapper.text()).toContain('工作台数据加载失败')
    expect(wrapper.findAll('button').some(button => button.text() === '重试')).toBe(true)
  })
})
