import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WorkflowNodeRunPanel from './WorkflowNodeRunPanel.vue'
import { getToolDetail } from '@/api/tools'
import { uploadFile } from '@/api/files'
import { createTask, getTaskDetail, prepareTaskRun } from '@/api/tasks'
import { useWorkflowStore } from '@/stores'
import i18n from '@/locales'

vi.mock('@/api/tools', () => ({
  getToolDetail: vi.fn()
}))

vi.mock('@/api/files', () => ({
  uploadFile: vi.fn()
}))

vi.mock('@/api/tasks', () => ({
  createTask: vi.fn(),
  getTaskDetail: vi.fn(),
  prepareTaskRun: vi.fn(),
  isTaskTerminalStatus: (status: string) => ['success', 'failure', 'canceled'].includes(status)
}))

function mockReadyPreparationPreview() {
  vi.mocked(prepareTaskRun).mockResolvedValue({
    code: 200,
    message: 'ok',
    data: {
      ready: true,
      project_id: 'project-1',
      tool_id: 'tool-ready',
      tool_version_id: 'version-ready',
      params: {},
      file_ids: [],
      input_bindings: {},
      requested_input_bindings: {},
      standard_input_uploads: {},
      binding_decisions: {},
      blocked_reason: null,
      resource_snapshot: null
    }
  } as never)
}

const stubs = {
  AAlert: { props: ['message'], template: '<div class="alert"><slot />{{ message }}</div>' },
  ASpin: { template: '<div class="spin"><slot /></div>' },
  AEmpty: { props: ['description'], template: '<div class="empty">{{ description }}</div>' },
  AForm: { template: '<form><slot /></form>' },
  AButton: { props: ['loading', 'disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  ATag: { template: '<span><slot /></span>' },
  ToolRunInputForm: {
    name: 'ToolRunInputForm',
    props: ['schema', 'formState', 'fileList', 'allowUploads', 'hiddenFieldKeys'],
    emits: ['update:selectedArtifact'],
    template: '<div class="tool-parameter-form" :data-allow-uploads="String(allowUploads)" :data-schema-fields="Object.keys(schema.properties).join(\',\')" :data-hidden-fields="(hiddenFieldKeys || []).join(\',\')" />'
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

function mockLvpocketToolDetail() {
  vi.mocked(getToolDetail).mockResolvedValue({
    code: 200,
    message: 'ok',
    data: {
      id: 'tool-lvpocket',
      slug: 'lvpocket-pocket-prediction',
      name: 'LVpocket Pocket Prediction',
      description: 'Predict protein binding pockets from a PDB structure',
      status: 'published',
      is_public: true,
      tags: [],
      usage_count: 0,
      view_count: 0,
      favorite_count: 0,
      gpu_required: true,
      created_at: '2026-08-20T00:00:00Z',
      current_version: {
        id: 'version-lvpocket',
        tool_id: 'tool-lvpocket',
        version: '1.0.0',
        config: {
          type: 'ssh_job',
          input_schema: {
            type: 'object',
            properties: {
              protein_pdb: {
                type: 'string',
                format: 'file',
                title: 'Protein PDB',
                'ui:accept': '.pdb'
              },
              model_choice: {
                type: 'string',
                default: 'auto',
                enum: ['auto', 'all_scpdb']
              },
              device: {
                type: 'string',
                default: 'auto',
                enum: ['auto', 'gpu', 'cpu']
              }
            },
            required: ['protein_pdb']
          }
        },
        is_active: true,
        deprecated: false,
        created_at: '2026-08-20T00:00:00Z'
      }
    }
  } as never)
}

function mockRoleAwareLvpocketToolDetail() {
  vi.mocked(getToolDetail).mockResolvedValue({
    code: 200,
    message: 'ok',
    data: {
      id: 'tool-lvpocket',
      slug: 'lvpocket-pocket-prediction',
      name: 'LVpocket Pocket Prediction',
      description: 'Predict protein binding pockets from a PDB structure',
      status: 'published',
      is_public: true,
      tags: [],
      usage_count: 0,
      view_count: 0,
      favorite_count: 0,
      gpu_required: true,
      created_at: '2026-08-20T00:00:00Z',
      current_version: {
        id: 'version-lvpocket',
        tool_id: 'tool-lvpocket',
        version: '1.0.0',
        config: {
          type: 'ssh_job',
          input_schema: {
            type: 'object',
            properties: {
              protein_pdb: {
                type: 'string',
                format: 'file',
                title: 'Protein PDB',
                'ui:accept': '.pdb'
              },
              model_choice: {
                type: 'string',
                default: 'auto',
                enum: ['auto', 'all_scpdb']
              },
              device: {
                type: 'string',
                default: 'auto',
                enum: ['auto', 'gpu', 'cpu']
              }
            },
            required: ['protein_pdb']
          }
        },
        is_active: true,
        deprecated: false,
        created_at: '2026-08-20T00:00:00Z'
      },
      contract: {
        contract_version: '2.0',
        slug: 'lvpocket-pocket-prediction',
        name: 'LVpocket Pocket Prediction',
        status: 'published',
        executor: { type: 'ssh_job' },
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
          inputs: [
            {
              name: 'protein',
              type: 'protein_structure@1',
              required: true,
              role_preferences: ['prepared_pdb', 'structure_file'],
              readiness_policy: 'prefer_prepared_warn_raw',
              suggested_preparation_tool: 'builtin-protein-preparation'
            }
          ],
          outputs: [{ name: 'pockets', type: 'binding_pocket@1', required: true }]
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
    vi.mocked(getTaskDetail).mockReset()
    vi.mocked(prepareTaskRun).mockReset()
    mockReadyPreparationPreview()
  })

  afterEach(() => {
    vi.useRealTimers()
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

  it('内置 artifact 输入节点独立运行时应提交标准上传绑定，由后端投影 builtin_inputs', async () => {
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

    wrapper.findComponent({ name: 'ToolRunInputForm' }).vm.$emit('update:selectedArtifact', 'protein', {
      id: 'file-protein',
      filename: 'protein.pdb',
      download_url: '/api/v1/files/file-protein/download'
    })
    await flushPromises()

    await wrapper.find('[data-testid="run-current-node"]').trigger('click')
    await flushPromises()

    const expectedPayload = {
      name: 'Protein Preparation · protein-preparation-node',
      tool_id: 'tool-protein-preparation',
      project_id: 'project-1',
      params: {},
      file_ids: undefined,
      standard_input_uploads: { protein: 'file-protein' }
    }
    expect(prepareTaskRun).toHaveBeenCalledWith(expectedPayload)
    expect(createTask).toHaveBeenCalledWith(expectedPayload)
  })

  it('上游推荐产物异步到达后，SSH 节点独立运行应自动绑定到文件入参', async () => {
    mockLvpocketToolDetail()
    vi.mocked(createTask).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        id: 'task-lvpocket',
        name: 'LVpocket Pocket Prediction',
        tool_id: 'tool-lvpocket',
        tool_slug: 'lvpocket-pocket-prediction',
        status: 'pending',
        progress: 0,
        created_at: '2026-08-20T00:00:00Z'
      }
    } as never)

    const wrapper = mount(WorkflowNodeRunPanel, {
      props: {
        nodeId: 'lvpocket-node',
        projectId: 'project-1',
        selectedToolSlug: 'lvpocket-pocket-prediction',
        availableTools: [
          {
            id: 'tool-lvpocket',
            slug: 'lvpocket-pocket-prediction',
            name: 'LVpocket Pocket Prediction'
          }
        ],
        recommendedArtifacts: []
      },
      global: { plugins: [i18n], stubs }
    })

    await flushPromises()

    await wrapper.setProps({
      recommendedArtifacts: [
        {
          edgeId: 'edge-fetch-pdb-to-lvpocket',
          sourceNodeId: 'fetch-pdb-node',
          semanticType: 'protein_structure@1',
          artifact: {
            id: 'file-pdb',
            filename: '1A2B.pdb',
            content_type: 'chemical/x-pdb',
            size_bytes: 1024,
            source_type: 'artifact',
            download_url: '/api/v1/files/file-pdb/download',
            task_id: 'task-fetch-pdb',
            tool_id: 'tool-fetch-pdb',
            tool_name: 'Fetch PDB Structure',
            tool_slug: 'builtin-fetch-pdb',
            semantic_type: 'protein_structure@1',
            created_at: '2026-08-20T00:01:00Z'
          }
        }
      ]
    })
    await flushPromises()

    expect(wrapper.text()).toContain('已自动绑定上游产物')
    expect(wrapper.text()).toContain('Fetch PDB Structure')
    expect(wrapper.find('.tool-parameter-form').attributes('data-hidden-fields')).toBe('protein_pdb')

    await wrapper.find('[data-testid="run-current-node"]').trigger('click')
    await flushPromises()

    expect(createTask).toHaveBeenCalledWith({
      name: 'LVpocket Pocket Prediction · lvpocket-node',
      tool_id: 'tool-lvpocket',
      project_id: 'project-1',
      params: {
        input_files: { protein_pdb: 'input/1A2B.pdb' },
        params: { model_choice: 'auto', device: 'auto' }
      },
      file_ids: ['file-pdb']
    })
  })

  it('标准产物推荐到达后，独立运行应提交 ArtifactVersion 绑定而不是 legacy 文件入参', async () => {
    mockRoleAwareLvpocketToolDetail()
    vi.mocked(createTask).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        id: 'task-lvpocket',
        name: 'LVpocket Pocket Prediction',
        tool_id: 'tool-lvpocket',
        tool_slug: 'lvpocket-pocket-prediction',
        status: 'pending',
        progress: 0,
        created_at: '2026-08-20T00:00:00Z'
      }
    } as never)

    const wrapper = mount(WorkflowNodeRunPanel, {
      props: {
        nodeId: 'lvpocket-node',
        projectId: 'project-1',
        selectedToolSlug: 'lvpocket-pocket-prediction',
        availableTools: [
          {
            id: 'tool-lvpocket',
            slug: 'lvpocket-pocket-prediction',
            name: 'LVpocket Pocket Prediction'
          }
        ],
        recommendedArtifacts: [
          {
            edgeId: 'edge-fetch-pdb-to-lvpocket',
            sourceNodeId: 'fetch-pdb-node',
            semanticType: 'protein_structure@1',
            artifact: {
              id: 'file-prepared',
              filename: 'prepared.pdb',
              content_type: 'chemical/x-pdb',
              size_bytes: 2048,
              source_type: 'artifact',
              download_url: '/api/v1/files/file-prepared/download',
              task_id: 'task-protein-preparation',
              tool_id: 'tool-protein-preparation',
              tool_name: 'Protein Preparation',
              tool_slug: 'builtin-protein-preparation',
              semantic_type: 'protein_structure@1',
              artifact_version_id: 'artifact-version-prepared',
              standard_artifact_role: 'prepared_pdb',
              created_at: '2026-08-20T00:01:00Z'
            }
          }
        ]
      },
      global: { plugins: [i18n], stubs }
    })

    await flushPromises()

    await wrapper.find('[data-testid="run-current-node"]').trigger('click')
    await flushPromises()

    expect(createTask).toHaveBeenCalledWith({
      name: 'LVpocket Pocket Prediction · lvpocket-node',
      tool_id: 'tool-lvpocket',
      project_id: 'project-1',
      params: { params: { model_choice: 'auto', device: 'auto' } },
      file_ids: undefined,
      input_bindings: { protein: 'artifact-version-prepared' }
    })
  })

  it('后端运行准备预览 blocked 时应展示原因且不创建任务', async () => {
    mockRoleAwareLvpocketToolDetail()
    vi.mocked(prepareTaskRun).mockResolvedValueOnce({
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
        requested_input_bindings: { protein: 'artifact-version-raw' },
        standard_input_uploads: {},
        binding_decisions: {
          protein: {
            status: 'needs_preparation',
            reason: 'Protein input requires a prepared PDB role.'
          }
        },
        blocked_reason: 'Protein input requires a prepared PDB role.',
        resource_snapshot: null
      }
    } as never)

    const wrapper = mount(WorkflowNodeRunPanel, {
      props: {
        nodeId: 'lvpocket-node',
        projectId: 'project-1',
        selectedToolSlug: 'lvpocket-pocket-prediction',
        availableTools: [
          {
            id: 'tool-lvpocket',
            slug: 'lvpocket-pocket-prediction',
            name: 'LVpocket Pocket Prediction'
          }
        ],
        recommendedArtifacts: [
          {
            edgeId: 'edge-fetch-pdb-to-lvpocket',
            sourceNodeId: 'fetch-pdb-node',
            semanticType: 'protein_structure@1',
            artifact: {
              id: 'file-raw',
              filename: 'raw.pdb',
              content_type: 'chemical/x-pdb',
              size_bytes: 1024,
              source_type: 'artifact',
              download_url: '/api/v1/files/file-raw/download',
              task_id: 'task-fetch-pdb',
              tool_id: 'tool-fetch-pdb',
              tool_name: 'Fetch PDB Structure',
              tool_slug: 'builtin-fetch-pdb',
              semantic_type: 'protein_structure@1',
              artifact_version_id: 'artifact-version-raw',
              standard_artifact_role: 'structure_file',
              created_at: '2026-08-20T00:01:00Z'
            }
          }
        ]
      },
      global: { plugins: [i18n], stubs }
    })

    await flushPromises()
    await wrapper.find('[data-testid="run-current-node"]').trigger('click')
    await flushPromises()

    expect(createTask).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Protein input requires a prepared PDB role.')
  })

  it('独立运行创建后应轮询任务终态并更新当前节点状态', async () => {
    vi.useFakeTimers()
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
    vi.mocked(getTaskDetail).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        id: 'task-fetch-pdb',
        name: 'Fetch PDB Structure',
        tool_id: 'tool-fetch-pdb',
        tool_slug: 'builtin-fetch-pdb',
        status: 'failure',
        progress: 0,
        progress_message: '任务失败',
        error_message: 'Task extra_data.project_id is required for standard artifacts',
        created_at: '2026-08-20T00:00:00Z',
        updated_at: '2026-08-20T00:00:02Z'
      }
    } as never)

    const workflowStore = useWorkflowStore()
    workflowStore.setNodeFormDraft('fetch-pdb-node', { pdb_id: '1ABC' })

    const wrapper = mount(WorkflowNodeRunPanel, {
      props: {
        nodeId: 'fetch-pdb-node',
        selectedToolSlug: 'builtin-fetch-pdb',
        availableTools: [
          {
            id: 'tool-fetch-pdb',
            slug: 'builtin-fetch-pdb',
            name: 'Fetch PDB Structure'
          }
        ],
        recommendedArtifacts: []
      },
      global: { plugins: [i18n], stubs }
    })

    await flushPromises()
    await wrapper.find('[data-testid="run-current-node"]').trigger('click')
    await flushPromises()
    expect(workflowStore.taskByNode['fetch-pdb-node']).toMatchObject({ status: 'pending' })

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(getTaskDetail).toHaveBeenCalledWith('task-fetch-pdb')
    expect(workflowStore.taskByNode['fetch-pdb-node']).toMatchObject({
      status: 'failure',
      error_message: 'Task extra_data.project_id is required for standard artifacts'
    })
  })

  it('挂载时应恢复轮询已绑定但未终止的节点任务', async () => {
    vi.useFakeTimers()
    mockFetchPdbToolDetail()
    vi.mocked(getTaskDetail).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        id: 'task-existing-fetch-pdb',
        name: 'Fetch PDB Structure',
        tool_id: 'tool-fetch-pdb',
        tool_slug: 'builtin-fetch-pdb',
        status: 'failure',
        progress: 0,
        progress_message: '任务失败',
        error_message: 'Task extra_data.project_id is required for standard artifacts',
        created_at: '2026-08-20T00:00:00Z',
        updated_at: '2026-08-20T00:00:02Z'
      }
    } as never)

    const workflowStore = useWorkflowStore()
    workflowStore.recordNodeTask('fetch-pdb-node', {
      id: 'task-existing-fetch-pdb',
      name: 'Fetch PDB Structure',
      tool_id: 'tool-fetch-pdb',
      tool_slug: 'builtin-fetch-pdb',
      status: 'running',
      progress: 0,
      created_at: '2026-08-20T00:00:00Z'
    })

    mount(WorkflowNodeRunPanel, {
      props: {
        nodeId: 'fetch-pdb-node',
        selectedToolSlug: 'builtin-fetch-pdb',
        availableTools: [
          {
            id: 'tool-fetch-pdb',
            slug: 'builtin-fetch-pdb',
            name: 'Fetch PDB Structure'
          }
        ],
        recommendedArtifacts: []
      },
      global: { plugins: [i18n], stubs }
    })

    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(getTaskDetail).toHaveBeenCalledWith('task-existing-fetch-pdb')
    expect(workflowStore.taskByNode['fetch-pdb-node']).toMatchObject({
      status: 'failure',
      error_message: 'Task extra_data.project_id is required for standard artifacts'
    })
  })
})
