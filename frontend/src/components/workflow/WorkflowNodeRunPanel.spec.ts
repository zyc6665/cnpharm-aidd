import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WorkflowNodeRunPanel from './WorkflowNodeRunPanel.vue'
import { getToolDetail } from '@/api/tools'
import { uploadFile } from '@/api/files'
import { createTask } from '@/api/tasks'
import { useWorkflowStore } from '@/stores'
import i18n from '@/locales'

vi.mock('@/api/tools', () => ({
  getToolDetail: vi.fn()
}))

vi.mock('@/api/files', () => ({
  uploadFile: vi.fn()
}))

vi.mock('@/api/tasks', () => ({
  createTask: vi.fn()
}))

const stubs = {
  AAlert: { template: '<div class="alert"><slot /></div>' },
  ASpin: { template: '<div class="spin"><slot /></div>' },
  AEmpty: { props: ['description'], template: '<div class="empty">{{ description }}</div>' },
  AForm: { template: '<form><slot /></form>' },
  AButton: { props: ['loading', 'disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  ATag: { template: '<span><slot /></span>' },
  ToolParameterForm: {
    name: 'ToolParameterForm',
    props: ['schema', 'formState', 'fileList', 'allowUploads'],
    emits: ['update:selectedArtifact'],
    template: '<div class="tool-parameter-form" :data-allow-uploads="String(allowUploads)" :data-schema-fields="Object.keys(schema.properties).join(\',\')" />'
  }
}

function mockFetchPdbToolDetail() {
  vi.mocked(getToolDetail).mockResolvedValue({
    code: 200,
    message: 'ok',
    data: {
      id: 'tool-fetch-pdb',
      slug: 'builtin-fetch-pdb',
      name: 'Fetch PDB Structure',
      description: 'Download a protein structure from RCSB PDB',
      status: 'published',
      is_public: true,
      tags: [],
      usage_count: 0,
      view_count: 0,
      favorite_count: 0,
      gpu_required: false,
      created_at: '2026-08-20T00:00:00Z',
      current_version: {
        id: 'version-fetch-pdb',
        tool_id: 'tool-fetch-pdb',
        version: '1.0.0',
        config: {
          type: 'builtin',
          input_schema: {
            type: 'object',
            properties: { pdb_id: { type: 'string', title: 'PDB ID' } },
            required: ['pdb_id']
          }
        },
        is_active: true,
        deprecated: false,
        created_at: '2026-08-20T00:00:00Z'
      }
    }
  } as never)
}

function mockProteinPreparationToolDetail() {
  vi.mocked(getToolDetail).mockResolvedValue({
    code: 200,
    message: 'ok',
    data: {
      id: 'tool-protein-preparation',
      slug: 'builtin-protein-preparation',
      name: 'Protein Preparation',
      description: 'Prepare protein structures for downstream docking',
      status: 'published',
      is_public: true,
      tags: [],
      usage_count: 0,
      view_count: 0,
      favorite_count: 0,
      gpu_required: false,
      created_at: '2026-08-20T00:00:00Z',
      current_version: {
        id: 'version-protein-preparation',
        tool_id: 'tool-protein-preparation',
        version: '1.0.0',
        config: {
          type: 'builtin',
          builtin_slug: 'builtin-protein-preparation',
          input_schema: {
            type: 'object',
            properties: {},
            required: []
          }
        },
        is_active: true,
        deprecated: false,
        created_at: '2026-08-20T00:00:00Z'
      },
      contract: {
        contract_version: '2.0',
        slug: 'builtin-protein-preparation',
        name: 'Protein Preparation',
        status: 'published',
        executor: { type: 'builtin' },
        schema: {
          input: { type: 'object', properties: {}, required: [] },
          output: { type: 'object', properties: {}, required: [] }
        },
        capability: {
          enabled: true,
          inputs: [],
          outputs: [],
          defaults: {}
        },
        artifacts: {
          inputs: [{ name: 'protein', type: 'protein_structure@1', required: true }],
          outputs: [{ name: 'prepared_protein', type: 'protein_structure@1', required: true }]
        },
        validation: { status: 'valid', errors: [] }
      }
    }
  } as never)
}

describe('WorkflowNodeRunPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(getToolDetail).mockReset()
    vi.mocked(uploadFile).mockReset()
    vi.mocked(createTask).mockReset()
  })

  it('工具列表异步补齐 id 后应加载真实工具并显示节点参数表单', async () => {
    mockFetchPdbToolDetail()

    const wrapper = mount(WorkflowNodeRunPanel, {
      props: {
        nodeId: 'fetch-pdb-node',
        selectedToolSlug: 'builtin-fetch-pdb',
        availableTools: [],
        recommendedArtifacts: []
      },
      global: { plugins: [i18n], stubs }
    })

    await flushPromises()
    expect(wrapper.text()).toContain('Select a real tool before configuring this node')
    expect(getToolDetail).not.toHaveBeenCalled()

    await wrapper.setProps({
      availableTools: [
        {
          id: 'tool-fetch-pdb',
          slug: 'builtin-fetch-pdb',
          name: 'Fetch PDB Structure',
          description: 'Download a protein structure from RCSB PDB'
        }
      ]
    })
    await flushPromises()

    expect(getToolDetail).toHaveBeenCalledWith('tool-fetch-pdb')
    expect(wrapper.find('.tool-parameter-form').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Select a real tool before configuring this node')
  })

  it('节点参数面板应允许上传并独立创建当前节点任务', async () => {
    mockFetchPdbToolDetail()
    vi.mocked(createTask).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        id: 'task-fetch-pdb',
        name: 'Fetch PDB Structure',
        tool_id: 'tool-fetch-pdb',
        tool_slug: 'builtin-fetch-pdb',
        status: 'pending',
        progress: 0,
        created_at: '2026-08-20T00:00:00Z'
      }
    } as never)

    const workflowStore = useWorkflowStore()
    workflowStore.setNodeFormDraft('fetch-pdb-node', { pdb_id: '1ABC' })

    const wrapper = mount(WorkflowNodeRunPanel, {
      props: {
        nodeId: 'fetch-pdb-node',
        projectId: 'project-1',
        selectedToolSlug: 'builtin-fetch-pdb',
        availableTools: [
          {
            id: 'tool-fetch-pdb',
            slug: 'builtin-fetch-pdb',
            name: 'Fetch PDB Structure',
            description: 'Download a protein structure from RCSB PDB'
          }
        ],
        recommendedArtifacts: []
      },
      global: { plugins: [i18n], stubs }
    })

    await flushPromises()
    expect(wrapper.find('.tool-parameter-form').attributes('data-allow-uploads')).toBe('true')

    await wrapper.find('[data-testid="run-current-node"]').trigger('click')
    await flushPromises()

    expect(createTask).toHaveBeenCalledWith({
      name: 'Fetch PDB Structure · fetch-pdb-node',
      tool_id: 'tool-fetch-pdb',
      project_id: 'project-1',
      params: { pdb_id: '1ABC' },
      file_ids: undefined
    })
    expect(workflowStore.taskByNode['fetch-pdb-node']).toMatchObject({
      id: 'task-fetch-pdb',
      tool_slug: 'builtin-fetch-pdb',
      status: 'pending'
    })
  })

  it('内置 artifact 输入节点独立运行时应提交标准 builtin_inputs 映射', async () => {
    mockProteinPreparationToolDetail()
    vi.mocked(createTask).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        id: 'task-protein-preparation',
        name: 'Protein Preparation',
        tool_id: 'tool-protein-preparation',
        tool_slug: 'builtin-protein-preparation',
        status: 'pending',
        progress: 0,
        created_at: '2026-08-20T00:00:00Z'
      }
    } as never)

    const wrapper = mount(WorkflowNodeRunPanel, {
      props: {
        nodeId: 'protein-preparation-node',
        projectId: 'project-1',
        selectedToolSlug: 'builtin-protein-preparation',
        availableTools: [
          {
            id: 'tool-protein-preparation',
            slug: 'builtin-protein-preparation',
            name: 'Protein Preparation'
          }
        ],
        recommendedArtifacts: []
      },
      global: { plugins: [i18n], stubs }
    })

    await flushPromises()
    expect(wrapper.find('.tool-parameter-form').attributes('data-schema-fields')).toBe('protein')

    wrapper.findComponent({ name: 'ToolParameterForm' }).vm.$emit('update:selectedArtifact', 'protein', {
      id: 'file-protein',
      filename: 'protein.pdb',
      download_url: '/api/v1/files/file-protein/download'
    })
    await flushPromises()

    await wrapper.find('[data-testid="run-current-node"]').trigger('click')
    await flushPromises()

    expect(createTask).toHaveBeenCalledWith({
      name: 'Protein Preparation · protein-preparation-node',
      tool_id: 'tool-protein-preparation',
      project_id: 'project-1',
      params: { builtin_inputs: { 'protein_structure@1': 'file-protein' } },
      file_ids: ['file-protein']
    })
  })
})
