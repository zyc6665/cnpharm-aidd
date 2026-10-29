import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { message } from 'ant-design-vue'
import ToolDetail from './Detail.vue'
import { getToolDetail, getToolExample } from '@/api/tools'
import { createTask, prepareTaskRun } from '@/api/tasks'
import { uploadFile } from '@/api/files'
import { useUserStore } from '@/stores'
import i18n from '@/locales'

const routerPush = vi.fn()
const routeState = vi.hoisted(() => ({
  params: { id: 'tool-lvpocket' } as Record<string, unknown>,
  query: { project_id: 'project-1' } as Record<string, unknown>,
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
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
  ArtifactFilePicker: {
    props: ['accept'],
    emits: ['update:uploadList', 'update:selectedArtifact'],
    template: '<button type="button" class="artifact-file-picker" @click="emitFile">pick file</button>',
    setup(props: { accept?: string }, { emit }: { emit: (event: string, ...args: unknown[]) => void }) {
      return {
        emitFile() {
          const name = props.accept?.includes('.pdb') ? 'protein.pdb' : 'molecules.csv'
          emit('update:uploadList', [
            {
              uid: `upload-${name}`,
              name,
              originFileObj: { name },
            },
          ])
        },
      }
    },
  },
  RouterLink: { template: '<a><slot /></a>' },
  AForm: { emits: ['finish'], template: '<form @submit.prevent="$emit(\'finish\')"><slot /></form>' },
  AFormItem: { props: ['label'], template: '<div><span class="form-label">{{ label }}</span><slot /></div>' },
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

function mockToolPackageV2Detail() {
  vi.mocked(getToolDetail).mockResolvedValue({
    code: 200,
    message: 'ok',
    data: {
      id: 'tool-molp-pc',
      slug: 'molp-pc',
      name: 'MolP-PC',
      description: 'Predict molecule properties',
      status: 'published',
      is_public: true,
      tags: [],
      statistics: { usage_count: 0, view_count: 0, favorite_count: 0 },
      current_version: {
        id: 'version-molp-pc',
        tool_id: 'tool-molp-pc',
        version: '2.0.0',
        config: {
          type: 'ssh_job',
          tool_package_manifest: {
            api_version: 'aidd.sciminer/tool-package',
            kind: 'ToolPackage',
            metadata: {
              slug: 'molp-pc',
              name: 'MolP-PC',
              version: '2.0.0',
              description: 'Predict molecule properties',
            },
            artifacts: {
              inputs: [
                { name: 'molecules', type: 'molecule_table@1', required: true },
              ],
              outputs: [
                { name: 'properties', type: 'molecule_table@1', required: true },
              ],
            },
            parameters_schema: { type: 'object', properties: {}, required: [] },
            runtime: {},
            variants: [],
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

function mockToolPackageV2DetailWithLegacyFileSchema() {
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
        version: '2.0.0',
        config: {
          type: 'ssh_job',
          input_schema: {
            type: 'object',
            properties: {
              protein_pdb: {
                type: 'string',
                format: 'file',
                title: 'Protein PDB',
                description: 'Protein receptor structure in PDB format.',
                'ui:accept': '.pdb',
              },
              model_choice: {
                type: 'string',
                title: 'Model weight',
                description: 'Manual choices map to new_best/*.hdf.',
                default: 'auto',
                enum: ['auto', 'all_scpdb'],
              },
              device: {
                type: 'string',
                title: 'Device',
                description: 'cpu disables CUDA for parity or troubleshooting.',
                default: 'auto',
                enum: ['auto', 'gpu', 'cpu'],
              },
            },
            required: ['protein_pdb'],
          },
          tool_package_manifest: {
            api_version: 'aidd.sciminer/tool-package',
            kind: 'ToolPackage',
            metadata: {
              slug: 'lvpocket-standard-pocket',
              name: 'LVpocket Standard Pocket Adapter',
              version: '2.0.0',
            },
            artifacts: {
              inputs: [
                { name: 'protein', type: 'protein_structure@1', required: true },
              ],
              outputs: [
                { name: 'pocket', type: 'binding_pocket@1', required: true },
              ],
            },
            parameters_schema: {
              type: 'object',
              properties: {
                model_choice: { type: 'string', default: 'auto', enum: ['auto', 'all_scpdb'] },
              },
              required: [],
            },
            runtime: {},
            variants: [],
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
    routeState.params = { id: 'tool-lvpocket' }
    routeState.query = { project_id: 'project-1' }
    routerPush.mockReset()
    vi.mocked(getToolDetail).mockReset()
    vi.mocked(getToolExample).mockReset()
    vi.mocked(createTask).mockReset()
    vi.mocked(prepareTaskRun).mockReset()
    vi.mocked(uploadFile).mockReset()
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

  it('runs declared file inputs from the standalone detail page with direct upload', async () => {
    routeState.params = { id: 'tool-molp-pc' }
    routeState.query = {}
    mockToolPackageV2Detail()
    vi.mocked(uploadFile).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: { id: 'file-upload-1', filename: 'molecules.csv' },
    } as never)
    vi.mocked(prepareTaskRun).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        ready: true,
        project_id: null,
        tool_id: 'tool-molp-pc',
        tool_version_id: 'version-molp-pc',
        params: {},
        file_ids: ['file-upload-1'],
        input_bindings: {},
        requested_input_bindings: {},
        standard_input_uploads: { molecules: 'file-upload-1' },
        binding_decisions: {},
        blocked_reason: null,
        resource_snapshot: null,
      },
    } as never)
    vi.mocked(createTask).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: { id: 'task-created' },
    } as never)

    const wrapper = mount(ToolDetail, {
      global: { plugins: [i18n], stubs },
    })

    await flushPromises()

    expect(wrapper.text()).not.toContain('Tool Package v2')
    expect(wrapper.text()).not.toContain('molecule_table@1')

    await wrapper.find('.artifact-file-picker').trigger('click')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const expectedPayload = {
      name: undefined,
      tool_id: 'tool-molp-pc',
      params: {},
      file_ids: undefined,
      standard_input_uploads: { molecules: 'file-upload-1' },
    }
    expect(uploadFile).toHaveBeenCalledWith({ name: 'molecules.csv' })
    expect(prepareTaskRun).toHaveBeenCalledWith(expectedPayload)
    expect(createTask).toHaveBeenCalledWith(expectedPayload)
    expect(routerPush).toHaveBeenCalledWith('/tasks/task-created')
  })

  it('shows declared parameters and submits their default values', async () => {
    routeState.params = { id: 'tool-lvpocket' }
    routeState.query = {}
    mockToolPackageV2DetailWithLegacyFileSchema()
    vi.mocked(uploadFile).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: { id: 'file-protein-1', filename: 'protein.pdb' },
    } as never)
    vi.mocked(prepareTaskRun).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        ready: true,
        project_id: null,
        tool_id: 'tool-lvpocket',
        tool_version_id: 'version-lvpocket',
        params: { params: { model_choice: 'auto', device: 'auto' } },
        file_ids: [],
        input_bindings: {},
        requested_input_bindings: {},
        standard_input_uploads: { protein: 'file-protein-1' },
        binding_decisions: {},
        blocked_reason: null,
        resource_snapshot: null,
      },
    } as never)
    vi.mocked(createTask).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: { id: 'task-created' },
    } as never)

    const wrapper = mount(ToolDetail, {
      global: { plugins: [i18n], stubs },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Protein PDB')
    expect(wrapper.text()).toContain('Model weight')
    expect(wrapper.text()).toContain('Device')
    expect(wrapper.findAll('.artifact-file-picker')).toHaveLength(1)

    await wrapper.find('.artifact-file-picker').trigger('click')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const expectedPayload = {
      name: undefined,
      tool_id: 'tool-lvpocket',
      params: { params: { model_choice: 'auto', device: 'auto' } },
      file_ids: undefined,
      standard_input_uploads: { protein: 'file-protein-1' },
    }
    expect(uploadFile).toHaveBeenCalledWith({ name: 'protein.pdb' })
    expect(prepareTaskRun).toHaveBeenCalledWith(expectedPayload)
    expect(createTask).toHaveBeenCalledWith(expectedPayload)
  })
})
