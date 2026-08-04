import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'
import AiddAgentPanel from './AiddAgentPanel.vue'
import { createProjectConversation, startProjectAgentRun } from '@/api/conversations'
import { listProjects } from '@/api/projects'
import { useUserStore } from '@/stores'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push })
}))

vi.mock('@/api/conversations', () => ({
  createProjectConversation: vi.fn(),
  startProjectAgentRun: vi.fn()
}))

vi.mock('@/api/projects', () => ({
  listProjects: vi.fn()
}))

const stubs = {
  ApartmentOutlined: true,
  DeleteOutlined: true,
  PlayCircleOutlined: true,
  ReloadOutlined: true,
  SyncOutlined: true,
  AAlert: { template: '<div><slot /><slot name="action" /></div>' },
  AButton: { template: '<button><slot /></button>' },
  ACheckbox: { template: '<label><slot /></label>' },
  AEmpty: true,
  AForm: { template: '<form><slot /></form>' },
  AFormItem: { template: '<label><slot /></label>' },
  APopconfirm: { template: '<span><slot /></span>' },
  ASelect: { template: '<select />' },
  ATag: { template: '<span><slot /></span>' },
  ATextarea: { template: '<textarea />' },
  ATimeline: { template: '<ol><slot /></ol>' },
  ATimelineItem: { template: '<li><slot /></li>' }
}

function renderPanel() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const userStore = useUserStore()
  userStore.token = 'token'
  userStore.authReady = true
  userStore.userInfo = {
    id: 'user-1',
    email: 'owner@example.com',
    username: 'owner',
    role: 'user',
    status: 'active',
    created_at: '2026-08-03T00:00:00Z',
    updated_at: '2026-08-03T00:00:00Z'
  }

  return mount(AiddAgentPanel, {
    global: {
      plugins: [pinia, i18n],
      stubs
    }
  })
}

describe('AiddAgentPanel draft assistant', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    push.mockReset()
    vi.mocked(listProjects).mockResolvedValue({
      data: {
        items: [
          {
            id: 'project-1',
            organization_id: 'organization-1',
            created_by: 'user-1',
            name: '口袋研究',
            goal: '识别口袋',
            status: 'active',
            model_policy: {},
            data_policy: {},
            membership: { id: 'membership-1', role: 'owner' },
            created_at: '2026-08-03T00:00:00Z',
            updated_at: '2026-08-03T00:00:00Z'
          }
        ]
      }
    } as never)
    vi.mocked(createProjectConversation).mockResolvedValue({
      data: { id: 'conversation-1', project_id: 'project-1', title: '首次分析', status: 'active' }
    } as never)
    vi.mocked(startProjectAgentRun).mockResolvedValue({
      data: { id: 'run-1', project_id: 'project-1', message: '识别口袋', intent: 'pocket_detection', status: 'input_required', requested_outputs: [], plan: {} }
    } as never)
  })

  it('进入项目研究会话并使用项目 agent-run 新接口', async () => {
    const wrapper = renderPanel()
    await flushPromises()

    expect(wrapper.text()).toContain('项目智能体')
    expect(wrapper.text()).not.toContain('运行智能体')
    expect(wrapper.text()).not.toContain('历史会话')
    expect(wrapper.text()).not.toContain('同步状态')

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(createProjectConversation).toHaveBeenCalledWith('project-1', expect.any(String))
    expect(startProjectAgentRun).toHaveBeenCalledWith('project-1', 'conversation-1', {
      goal: expect.any(String)
    })
    expect(push).toHaveBeenCalledWith({
      name: 'ProjectResearch',
      params: { projectId: 'project-1', conversationId: 'conversation-1' }
    })
  })
})
