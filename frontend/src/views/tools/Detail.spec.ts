import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { message } from 'ant-design-vue'
import ToolDetail from './Detail.vue'
import { getToolDetail, getToolExample } from '@/api/tools'
import { createTask, prepareTaskRun } from '@/api/tasks'
import { useUserStore } from '@/stores'
import i18n from '@/locales'

const routerPush = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'tool-lvpocket' }, query: { project_id: 'project-1' } }),
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('ant-design-vue', () => ({
  message: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

vi.mock('@/api/tools', () => ({
  getToolList: vi.fn(),
  getToolDetail: vi.fn(),
  getCategories: vi.fn(),
  getTags: vi.fn(),
  getWorkbenchGroups: vi.fn(),
  getWorkflowToolOptions: vi.fn(),
  favoriteTool: vi.fn(),
  unfavoriteTool: vi.fn(),
  applyToolExample: vi.fn(),
  getToolExample: vi.fn(),
  previewToolExampleFile: vi.fn(),
}))

vi.mock('@/api/files', () => ({
  uploadFile: vi.fn(),
  convertSdfToPdb: vi.fn(),
}))

vi.mock('@/api/artifacts', () => ({
  getProjectArtifacts: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  getTaskList: vi.fn(),
  getTaskDetail: vi.fn(),
  createTask: vi.fn(),
  cancelTask: vi.fn(),
  retryTask: vi.fn(),
  deleteTask: vi.fn(),
  prepareTaskRun: vi.fn(),
}))

const stubs = {
  AppPageHeader: { template: '<header><slot name="actions" /><slot /></header>' },
  SkeletonDetail: { template: '<div />' },
  SkeletonCard: { template: '<div />' },
  ToolExamplePanel: { template: '<div />' },
  ArtifactFilePicker: { template: '<div />' },
  RouterLink: { template: '<a><slot /></a>' },
  AForm: { emits: ['finish'], template: '<form @submit.prevent="$emit(\'finish\')"><slot /></form>' },
  AFormItem: { template: '<div><slot /></div>' },
  ASpace: { template: '<div><slot /></div>' },
  AButton: {
    props: ['disabled', 'htmlType'],
    template: '<button :type="htmlType || \'button\'" :disabled="disabled"><slot /></button>',
  },
  AInput: { template: '<input />' },
  AInputNumber: { template: '<input />' },
  ASelect: { template: '<select><slot /></select>' },
  ASelectOption: { template: '<option><slot /></option>' },
  AUpload: { template: '<div><slot /></div>' },
  ATag: { template: '<span><slot /></span>' },
  AAlert: { props: ['message'], template: '<div>{{ message }}</div>' },
  AModal: { template: '<div><slot /></div>' },
  AEmpty: { template: '<div />' },
  ToolOutlined: { template: '<i />' },
  HeartOutlined: { template: '<i />' },
  HeartFilled: { template: '<i />' },
  PlayCircleOutlined: { template: '<i />' },
  EyeOutlined: { template: '<i />' },
  TagOutlined: { template: '<i />' },
  InfoCircleOutlined: { template: '<i />' },
  FileTextOutlined: { template: '<i />' },
}

function mockToolDetail() {
  vi.mocked(getToolDetail).mockResolvedValue({
    code: 200,
    message: 'ok',
    data: {
      id: 'tool-lvpocket',
      slug: 'lvpocket-pocket-prediction',
      name: 'LVpocket Pocket Prediction',
      description: 'Predict protein pockets',
      status: 'published',
      is_public: true,
      tags: [],
      statistics: { usage_count: 0, view_count: 0, favorite_count: 0 },
      current_version: {
        id: 'version-lvpocket',
        tool_id: 'tool-lvpocket',
        version: '1.0.0',
        config: {
          type: 'ssh_job',
          input_schema: {
            type: 'object',
            properties: { model_choice: { type: 'string', default: 'auto' } },
            required: [],
          },
        },
        is_active: true,
        deprecated: false,
        created_at: '2026-08-20T00:00:00Z',
      },
      created_at: '2026-08-20T00:00:00Z',
    },
  } as never)
  vi.mocked(getToolExample).mockResolvedValue({ code: 200, message: 'ok', data: null } as never)
}

describe('ToolDetail run preparation preview', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routerPush.mockReset()
    vi.mocked(getToolDetail).mockReset()
    vi.mocked(getToolExample).mockReset()
    vi.mocked(createTask).mockReset()
    vi.mocked(prepareTaskRun).mockReset()
    vi.mocked(message.error).mockReset()
    vi.mocked(message.success).mockReset()

    const userStore = useUserStore()
    userStore.token = 'token'
  })

  it('stops task creation and shows backend reason when preparation preview is blocked', async () => {
    mockToolDetail()
    vi.mocked(prepareTaskRun).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        ready: false,
        project_id: 'project-1',
        tool_id: 'tool-lvpocket',
        tool_version_id: 'version-lvpocket',
        params: {},
        file_ids: [],
        input_bindings: {},
        requested_input_bindings: {},
        standard_input_uploads: {},
        binding_decisions: {
          protein: {
            status: 'needs_preparation',
            reason: 'Protein input requires a prepared PDB role.',
          },
        },
        blocked_reason: 'Protein input requires a prepared PDB role.',
        resource_snapshot: null,
      },
    } as never)

    const wrapper = mount(ToolDetail, {
      global: { plugins: [i18n], stubs },
    })

    await flushPromises()
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(prepareTaskRun).toHaveBeenCalled()
    expect(createTask).not.toHaveBeenCalled()
    expect(routerPush).not.toHaveBeenCalledWith('/tasks/task-created')
    expect(message.error).toHaveBeenCalledWith('Protein input requires a prepared PDB role.')
  })
})
