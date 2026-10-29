import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectOverview from './Overview.vue'
import { getProjectOverview } from '@/api/projects'
import { getAllProjectArtifacts } from '@/api/artifacts'

const routerReplace = vi.fn()
let routeQuery: Record<string, string | undefined> = {}

vi.mock('vue-router', async importOriginal => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ params: { projectId: 'project-1' }, query: routeQuery }),
    useRouter: () => ({ push: vi.fn(), replace: routerReplace })
  }
})

vi.mock('@/api/projects', () => ({
  getProjectOverview: vi.fn()
}))

vi.mock('@/api/artifacts', () => ({
  buildArtifactVersionDownloadUrl: (artifactId: string, versionId: string) =>
    `/api/v1/artifacts/${artifactId}/versions/${versionId}/download`,
  getAllProjectArtifacts: vi.fn()
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
    role: 'owner',
    membership: { id: 'membership-1', role: 'owner' },
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-31T08:30:00Z'
  },
  counts: { artifacts: 1, tasks: 1, workflows: 1 },
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
    routeQuery = {}
    vi.mocked(getProjectOverview).mockResolvedValue({ data: overview } as never)
    vi.mocked(getAllProjectArtifacts).mockResolvedValue({ data: { items: [] } } as never)
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
    expect(wrapper.text()).toContain('EGFR pocket')
    expect(wrapper.text()).toContain('项目口袋识别')
    expect(wrapper.text()).toContain('口袋到分子生成')
    expect(wrapper.text()).not.toContain('科研白板')
    const workflowEntry = wrapper
      .findAll('a')
      .find(link => link.text().includes('打开工作流'))
    const taskListEntry = wrapper
      .findAll('a')
      .find(link => link.text().includes('全部任务'))
    expect(taskListEntry?.attributes('href')).toBe('/tasks?project_id=project-1')
    expect(workflowEntry?.attributes('href')).toBe('/projects/project-1/workflow')
    expect(wrapper.find('[data-testid="open-targets"]').attributes('href')).toBe(
      '/projects/project-1/targets'
    )
    // 步骤 3 已删除 /projects/:projectId/research 路由，总览页不能再指向它（会 404）。
    expect(wrapper.find('[data-testid="open-research"]').exists()).toBe(false)
  })

  it('Artifact 常用筛选调用项目 Artifact 检索接口', async () => {
    vi.mocked(getAllProjectArtifacts).mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 'artifact-molp-pc',
            project_id: 'project-1',
            artifact_type: 'molecule_table',
            semantic_type: 'molecule_table@1',
            standard_type: 'molecule_table',
            standard_version: 1,
            name: 'MolP-PC ADMET table',
            latest_version: {
              id: 'artifact-version-molp-pc',
              version: 1,
              filename: 'molp-pc.csv',
              content_type: 'text/csv',
              size_bytes: 4096,
              sha256: 'b'.repeat(64),
              status: 'available',
              created_at: '2026-09-09T00:00:00Z'
            },
            created_at: '2026-09-09T00:00:00Z',
            updated_at: '2026-09-09T00:00:00Z'
          }
        ]
      }
    } as never)
    const wrapper = renderOverview()
    await flushPromises()

    const molpPcFilter = wrapper.findAll('[data-testid="artifact-filter-preset"]')
      .find(button => button.text() === 'MolP-PC')
    expect(molpPcFilter).toBeDefined()

    await molpPcFilter!.trigger('click')
    await flushPromises()

    expect(getAllProjectArtifacts).toHaveBeenCalledWith('project-1', {
      metadata_model_name: 'MolP-PC'
    })
    expect(wrapper.text()).toContain('MolP-PC ADMET table')
    expect(wrapper.text()).not.toContain('EGFR pocket')
  })

  it('Artifact 筛选视图写入 URL 并可从 URL 恢复', async () => {
    vi.mocked(getAllProjectArtifacts).mockResolvedValue({ data: { items: [] } } as never)
    const wrapper = renderOverview()
    await flushPromises()

    await wrapper.findAll('[data-testid="artifact-filter-preset"]')
      .find(button => button.text() === 'MolP-PC')!
      .trigger('click')
    await flushPromises()

    expect(routerReplace).toHaveBeenCalledWith({ query: { artifact_filter: 'molp_pc' } })

    vi.clearAllMocks()
    routeQuery = { artifact_filter: 'molecule_table' }
    vi.mocked(getProjectOverview).mockResolvedValue({ data: overview } as never)
    vi.mocked(getAllProjectArtifacts).mockResolvedValue({ data: { items: [] } } as never)
    renderOverview()
    await flushPromises()

    expect(getAllProjectArtifacts).toHaveBeenCalledWith('project-1', {
      standard_type: 'molecule_table'
    })
  })
})
