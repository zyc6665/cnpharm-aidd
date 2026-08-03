import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'
import AiddAgentPanel from './AiddAgentPanel.vue'
import { createAiddAgentRun } from '@/api/agents'
import { listProjects } from '@/api/projects'
import { useUserStore } from '@/stores'

vi.mock('@/api/agents', () => ({
  createAiddAgentRun: vi.fn(),
  createAiddWorkflowDraft: vi.fn()
}))

vi.mock('@/api/files', () => ({
  uploadFile: vi.fn()
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
  UploadOutlined: true,
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
  ATimelineItem: { template: '<li><slot /></li>' },
  AUpload: { template: '<div><slot /></div>' }
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
  })

  it('不再暴露旧智能体运行、历史、同步和取消入口', async () => {
    const wrapper = renderPanel()
    await flushPromises()

    expect(wrapper.text()).toContain('工作流草稿')
    expect(wrapper.text()).not.toContain('运行智能体')
    expect(wrapper.text()).not.toContain('历史会话')
    expect(wrapper.text()).not.toContain('同步状态')
    expect(createAiddAgentRun).not.toHaveBeenCalled()
  })
})
