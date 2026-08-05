import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectOverview from './Overview.vue'
import { getProjectOverview } from '@/api/projects'

vi.mock('vue-router', async importOriginal => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ params: { projectId: 'project-1' } }),
    useRouter: () => ({ push: vi.fn() })
  }
})

vi.mock('@/api/projects', () => ({
  getProjectOverview: vi.fn()
}))

const overview = {
  project: {
    id: 'project-1',
    organization_id: 'organization-1',
    created_by: 'user-1',
    name: 'EGFR 口袋研究',
    goal: '寻找可成药结合口袋',
    status: 'active',
    model_policy: {},
    data_policy: {},
    membership: { id: 'membership-1', role: 'owner' },
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-31T08:30:00Z'
  },
  counts: { artifacts: 1, tasks: 1, workflows: 1, boards: 1 },
  artifacts: [
    {
      id: 'artifact-1',
      project_id: 'project-1',
      artifact_type: 'binding_pocket',
      semantic_type: 'binding_pocket',
      standard_type: 'binding_pocket',
      standard_version: 1,
      name: 'EGFR pocket',
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
      created_at: '2026-07-31T08:20:00Z',
      updated_at: '2026-07-31T08:20:00Z'
    }
  ],
  tasks: [
    {
      id: 'task-1',
      name: '项目口袋识别',
      status: 'running',
      progress: 35,
      tool_id: 'tool-1',
      tool_name: 'LVpocket',
      tool_slug: 'lvpocket',
      created_at: '2026-07-31T08:00:00Z',
      updated_at: '2026-07-31T08:10:00Z'
    }
  ],
  workflows: [
    {
      id: 'workflow-1',
      project_id: 'project-1',
      name: '口袋到分子生成',
      status: 'draft',
      created_at: '2026-07-31T08:00:00Z',
      updated_at: '2026-07-31T08:00:00Z'
    }
  ],
  boards: [
    {
      id: 'board-1',
      project_id: 'project-1',
      name: '口袋分析白板',
      node_count: 1,
      created_at: '2026-07-31T08:00:00Z',
      updated_at: '2026-07-31T08:00:00Z'
    }
  ]
}

function renderOverview() {
  return mount(ProjectOverview, {
    global: {
      stubs: {
        ProjectWorkspaceNav: true,
        RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
        AButton: { template: '<button><slot /></button>' },
        AAlert: { template: '<div role="alert">{{ $attrs.message }}<slot /></div>' },
        ASkeleton: true,
        AEmpty: { props: ['description'], template: '<div>{{ description }}</div>' }
      }
    }
  })
}

describe('ProjectOverview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getProjectOverview).mockResolvedValue({ data: overview } as never)
  })

  it('展示项目总览、最近资源和进入研究会话入口', async () => {
    const wrapper = renderOverview()
    await flushPromises()

    expect(getProjectOverview).toHaveBeenCalledWith('project-1')
    expect(wrapper.text()).toContain('EGFR 口袋研究')
    expect(wrapper.text()).toContain('寻找可成药结合口袋')
    expect(wrapper.text()).toContain('Artifact')
    expect(wrapper.text()).toContain('任务')
    expect(wrapper.text()).toContain('工作流')
    expect(wrapper.text()).toContain('白板')
    expect(wrapper.text()).toContain('EGFR pocket')
    expect(wrapper.text()).toContain('项目口袋识别')
    expect(wrapper.text()).toContain('口袋到分子生成')
    expect(wrapper.text()).toContain('口袋分析白板')
    const workflowEntry = wrapper
      .findAll('a')
      .find(link => link.text().includes('打开工作流'))
    const taskListEntry = wrapper
      .findAll('a')
      .find(link => link.text().includes('全部任务'))
    expect(taskListEntry?.attributes('href')).toBe('/tasks?project_id=project-1')
    expect(workflowEntry?.attributes('href')).toBe('/projects/project-1/workflow')
    expect(wrapper.find('[data-testid="open-research"]').attributes('href')).toBe(
      '/projects/project-1/research'
    )
  })
})
