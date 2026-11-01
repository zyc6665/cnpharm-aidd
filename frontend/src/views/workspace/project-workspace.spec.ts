import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'
import WorkspaceView from './index.vue'
import { archiveProject, deleteProject, listProjects } from '@/api/projects'
import { getWorkspaceOverview } from '@/api/workspace'

vi.mock('@/api/projects', () => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  archiveProject: vi.fn(),
  deleteProject: vi.fn()
}))
vi.mock('@/api/tasks', () => ({ getTaskCounts: vi.fn() }))
vi.mock('@/api/workspace', () => ({ getWorkspaceOverview: vi.fn() }))

const projects = [
  {
    id: 'project-1',
    organization_id: 'organization-1',
    created_by: 'user-1',
    name: 'EGFR 口袋研究',
    goal: '寻找可成药结合口袋',
    status: 'active',
    model_policy: {},
    data_policy: {},
    role: 'owner',
    membership: { id: 'membership-1', role: 'owner' },
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-31T08:30:00Z'
  }
]

const overview = {
  attention_task_count: 2,
  task_status_counts: { pending: 1, running: 0, success: 2, failure: 1, canceled: 0 },
  tasks: [
    {
      id: 'task-approval',
      name: 'LVpocket 执行审批',
      status: 'pending',
      progress: 0,
      tool_id: 'lvpocket',
      created_at: '2026-07-31T08:00:00Z',
      updated_at: '2026-07-31T08:00:00Z'
    },
    {
      id: 'task-failed',
      name: '口袋识别',
      status: 'failure',
      progress: 72,
      error_message: '远程执行节点不可用',
      tool_id: 'lvpocket',
      created_at: '2026-07-31T07:00:00Z',
      updated_at: '2026-07-31T07:10:00Z'
    }
  ],
  workflows: [],
  artifacts: [
    {
      id: 'artifact-1',
      project_id: 'project-1',
      artifact_type: 'binding_pocket',
      semantic_type: 'binding_pocket',
      standard_type: 'binding_pocket',
      standard_version: 1,
      name: 'EGFR 口袋',
      latest_version: {
        id: 'artifact-version-1',
        version: 1,
        filename: 'egfr-pocket.pdb',
        content_type: 'chemical/x-pdb',
        size_bytes: 2048,
        sha256: 'a'.repeat(64),
        status: 'available',
        created_at: '2026-07-31T08:20:00Z'
      },
      updated_at: '2026-07-31T08:20:00Z'
    }
  ],
  files: [],
  frequent_tools: [{ id: 'tool-1', name: '不应显示的常用工具', slug: 'legacy', usage_count: 8 }]
}

const stubs = {
  RouterLink: { props: ['to'], template: '<a><slot /></a>' },
  AButton: { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  AAlert: {
    template: '<div role="alert">{{ $attrs.message }}<slot /><slot name="action" /></div>'
  },
  ASkeleton: { template: '<div data-testid="loading">加载中</div>' },
  AEmpty: { props: ['description'], template: '<div>{{ description }}</div>' },
  AModal: { template: '<div><slot /></div>' },
  AForm: { template: '<form><slot /></form>' },
  AFormItem: { template: '<label><slot /></label>' },
  AInput: { template: '<input />' },
  ATextarea: { template: '<textarea />' },
  APopconfirm: {
    template: '<span @click="$emit(\'confirm\')"><slot /></span>'
  },
  PlusOutlined: true,
  FolderOpenOutlined: true,
  FileOutlined: true,
  WarningOutlined: true
}

function renderWorkspace() {
  return mount(WorkspaceView, {
    global: {
      plugins: [i18n],
      stubs,
      mocks: { $router: { push: vi.fn() } }
    }
  })
}

describe('Project workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listProjects).mockResolvedValue({ data: { items: projects } } as never)
    vi.mocked(getWorkspaceOverview).mockResolvedValue({ data: overview } as never)
    vi.mocked(archiveProject).mockResolvedValue({
      data: { ...projects[0]!, status: 'archived' }
    } as never)
    vi.mocked(deleteProject).mockResolvedValue({ data: { id: projects[0]!.id } } as never)
  })

  it('首屏聚焦新建项目、最近项目、待处理任务和最近 Artifact', async () => {
    const wrapper = renderWorkspace()
    await flushPromises()

    expect(wrapper.text()).toContain('新建项目')
    expect(wrapper.text()).toContain('最近项目')
    expect(wrapper.text()).toContain('EGFR 口袋研究')
    expect(wrapper.text()).toContain('需要关注的任务')
    expect(wrapper.text()).toContain('LVpocket 执行审批')
    expect(wrapper.text()).toContain('远程执行节点不可用')
    expect(wrapper.text()).toContain('最近 Artifact')
    expect(wrapper.text()).toContain('EGFR 口袋')
    // 类型显示中文名而不是 ``binding_pocket@1`` 这种协议标识；文件名降到次要行。
    expect(wrapper.text()).toContain('结合口袋')
    expect(wrapper.text()).toContain('egfr-pocket.pdb')
    expect(wrapper.text()).not.toContain('binding_pocket@1')
    expect(wrapper.find('.artifact-row').attributes('href')).toBe(
      '/api/v1/artifacts/artifact-1/versions/artifact-version-1/download'
    )
    expect(wrapper.text()).not.toContain('任务状态概览')
    expect(wrapper.text()).not.toContain('常用工具')
    expect(wrapper.text()).not.toContain('不应显示的常用工具')
  })

  it('无研究记录时提供明确的项目、任务和 Artifact 空状态', async () => {
    vi.mocked(listProjects).mockResolvedValue({ data: { items: [] } } as never)
    vi.mocked(getWorkspaceOverview).mockResolvedValue({
      data: { ...overview, attention_task_count: 0, tasks: [], artifacts: [], files: [] }
    } as never)

    const wrapper = renderWorkspace()
    await flushPromises()

    expect(wrapper.text()).toContain('还没有研究项目')
    expect(wrapper.text()).toContain('暂无待审批或失败任务')
    expect(wrapper.text()).toContain('暂无 Artifact')
  })

  it('任一首页接口失败时展示重试操作并重新加载全部数据', async () => {
    vi.mocked(listProjects).mockRejectedValueOnce(new Error('network'))
    const wrapper = renderWorkspace()
    await flushPromises()

    expect(wrapper.text()).toContain('研究工作台加载失败')
    const retry = wrapper.findAll('button').find(button => button.text() === '重试')
    expect(retry).toBeDefined()

    await retry!.trigger('click')
    await flushPromises()
    expect(listProjects).toHaveBeenCalledTimes(2)
    expect(getWorkspaceOverview).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('EGFR 口袋研究')
  })

  it('归档项目后无需刷新即可从最近项目列表移除', async () => {
    const wrapper = renderWorkspace()
    await flushPromises()

    const archive = wrapper.findAll('button').find(button => button.text() === '归档')
    expect(archive).toBeDefined()
    await archive!.trigger('click')
    await flushPromises()

    expect(archiveProject).toHaveBeenCalledWith('project-1')
    expect(wrapper.text()).not.toContain('EGFR 口袋研究')
    expect(wrapper.text()).toContain('还没有研究项目')
  })

  it('删除项目后无需刷新即可从最近项目列表移除', async () => {
    const wrapper = renderWorkspace()
    await flushPromises()

    const deleteButton = wrapper.findAll('button').find(button => button.text() === '删除')
    expect(deleteButton).toBeDefined()
    await deleteButton!.trigger('click')
    await flushPromises()

    expect(deleteProject).toHaveBeenCalledWith('project-1')
    expect(wrapper.text()).not.toContain('EGFR 口袋研究')
    expect(wrapper.text()).toContain('还没有研究项目')
  })
})
