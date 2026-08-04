import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'
import WorkflowView from './index.vue'
import { useWorkflowDefinitionsStore } from '@/stores'
import {
  createWorkflowDefinition,
  createWorkflowRun,
  deleteWorkflowDefinition,
  getWorkflowDefinitions,
  getWorkflowRun,
  getWorkflowRuns,
  updateWorkflowDefinition,
} from '@/api/workflows'

const push = vi.fn()
let routeQuery: Record<string, string | undefined> = {}

vi.mock('vue-router', async importOriginal => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ query: routeQuery }),
    useRouter: () => ({ push }),
  }
})

vi.mock('@/api/workflows', () => ({
  createWorkflowDefinition: vi.fn(),
  createWorkflowRun: vi.fn(),
  deleteWorkflowDefinition: vi.fn(),
  getWorkflowDefinition: vi.fn(),
  getWorkflowDefinitions: vi.fn(),
  getWorkflowRun: vi.fn(),
  getWorkflowRuns: vi.fn(),
  syncWorkflowRun: vi.fn(),
  updateWorkflowDefinition: vi.fn(),
}))

const stubs = {
  AppPageHeader: {
    props: ['title', 'subtitle'],
    template: '<header><h1>{{ title }}</h1><p>{{ subtitle }}</p></header>',
  },
  ATabs: { template: '<section><slot /></section>' },
  ATabPane: { template: '<section><slot /></section>' },
  AInput: {
    props: ['placeholder', 'value'],
    emits: ['update:value'],
    template: '<label>{{ placeholder }}<input :value="value" /></label>',
  },
  ASelect: {
    props: ['placeholder', 'options', 'value'],
    emits: ['change'],
    template: `
      <label>
        {{ placeholder }}
        <select />
        <button
          v-for="option in options"
          :key="option.value"
          class="select-option"
          type="button"
          @click="$emit('change', option.value)"
        >
          {{ option.label }}
        </button>
      </label>
    `,
  },
  ASpace: { template: '<div><slot /></div>' },
  AButton: {
    props: ['disabled'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  ATag: { template: '<span><slot /></span>' },
  APopconfirm: {
    emits: ['confirm'],
    template: '<span class="popconfirm" @click="$emit(\'confirm\')"><slot /></span>',
  },
  AEmpty: true,
  AiddAgentPanel: {
    emits: ['draftGenerated'],
    template: `
      <button
        class="emit-agent-draft"
        type="button"
        @click="$emit('draftGenerated', {
          name: 'Agent Draft',
          description: 'Generated from agent',
          intent: 'pocket',
          definition: {
            nodes: [{
              id: 'pocket_prediction',
              kind: 'tool',
              tool_slug: 'lvpocket',
              artifact_input_slots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
              artifact_outputs: [{ name: 'pocket', type: 'binding_pocket@1', required: true }]
            }],
            edges: []
          },
          input_files: { 'protein_structure@1': 'artifact-version-1' },
          requested_outputs: ['binding_pocket@1'],
          analysis_trace: []
        }, 'project-1')"
      >
        生成测试草稿
      </button>
    `,
  },
  WorkflowNodeInspector: true,
  WorkflowNodeStatusBadge: true,
  WorkflowPreflightPanel: true,
  WorkflowResultsReportPanel: true,
  WorkflowRunHistoryPanel: true,
  WorkflowRunInputPanel: true,
  WorkflowRunStatusPanel: true,
  WorkflowCanvasBoard: true,
  WorkflowCanvasToolbar: true,
  WorkflowToolPalette: true,
}

function renderWorkflow() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(WorkflowView, {
    global: {
      plugins: [pinia, i18n],
      stubs,
    },
  })
}

describe('free workflow workbench', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeQuery = {}
    localStorage.clear()
    sessionStorage.clear()
    vi.mocked(getWorkflowDefinitions).mockResolvedValue({
      data: { items: [], total: 0, page: 1, page_size: 100, total_pages: 0 },
    } as never)
    vi.mocked(createWorkflowDefinition).mockResolvedValue({
      data: {
        id: 'flow-1',
        user_id: 'user-1',
        name: '未命名流程',
        description: null,
        template_id: 'free-canvas',
        nodes: [],
        edges: [],
        selected_tool_by_node: {},
        artifact_bindings_by_node: {},
        status: 'draft',
        created_at: '2026-07-31T00:00:00Z',
        updated_at: '2026-07-31T00:00:00Z',
      },
    } as never)
    vi.mocked(updateWorkflowDefinition).mockResolvedValue({
      data: {
        id: 'flow-1',
        user_id: 'user-1',
        name: '未命名流程',
        description: null,
        template_id: 'free-canvas',
        nodes: [],
        edges: [],
        selected_tool_by_node: {},
        artifact_bindings_by_node: {},
        status: 'archived',
        created_at: '2026-07-31T00:00:00Z',
        updated_at: '2026-07-31T00:00:00Z',
      },
    } as never)
    vi.mocked(deleteWorkflowDefinition).mockResolvedValue({ data: null } as never)
    vi.mocked(getWorkflowRuns).mockResolvedValue({
      data: { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 },
    } as never)
    vi.mocked(getWorkflowRun).mockResolvedValue({
      data: {
        id: 'run-1',
        owner_id: 'user-1',
        workflow_definition_id: 'flow-1',
        project_id: 'project-1',
        name: '未命名流程',
        status: 'pending',
        definition: { nodes: [], edges: [] },
        input_files: {},
        execution_order: [],
        node_states: {},
        artifact_lineage: {},
        created_at: '2026-07-31T00:00:00Z',
        updated_at: '2026-07-31T00:00:00Z',
      },
    } as never)
    vi.mocked(createWorkflowRun).mockResolvedValue({
      data: {
        id: 'run-1',
        owner_id: 'user-1',
        workflow_definition_id: 'flow-1',
        project_id: 'project-1',
        name: '未命名流程',
        status: 'pending',
        definition: { nodes: [], edges: [] },
        input_files: {},
        execution_order: [],
        node_states: {},
        artifact_lineage: {},
        created_at: '2026-07-31T00:00:00Z',
        updated_at: '2026-07-31T00:00:00Z',
      },
    } as never)
  })

  it('默认展示流程语言，并移除固定模板选择入口', async () => {
    const wrapper = renderWorkflow()
    await flushPromises()

    expect(wrapper.text()).toContain('流程名称')
    expect(wrapper.text()).toContain('已保存流程')
    expect(wrapper.text()).not.toContain('模板选择')
    expect(wrapper.text()).not.toContain('工作流模板')
    expect(wrapper.text()).not.toContain('模板图谱')
  })

  it('保存默认自由流程时写入 WorkflowDefinition，不使用旧模板入口', async () => {
    const wrapper = renderWorkflow()
    await flushPromises()

    const saveButton = wrapper.findAll('button').find(button => button.text() === '保存')
    expect(saveButton).toBeDefined()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(createWorkflowDefinition).toHaveBeenCalledWith(expect.objectContaining({
      name: '未命名流程',
      template_id: 'free-canvas',
      nodes: [],
      edges: [],
      selected_tool_by_node: {},
      artifact_bindings_by_node: {},
      status: 'draft',
    }))
  })

  it('项目模式保存和运行都使用项目作用域的 WorkflowDefinition', async () => {
    routeQuery = { project_id: 'project-1' }
    vi.mocked(createWorkflowDefinition).mockResolvedValue({
      data: {
        id: 'flow-1',
        project_id: 'project-1',
        user_id: 'user-1',
        name: '未命名流程',
        description: null,
        template_id: 'free-canvas',
        nodes: [],
        edges: [],
        selected_tool_by_node: {},
        artifact_bindings_by_node: {},
        status: 'draft',
        created_at: '2026-07-31T00:00:00Z',
        updated_at: '2026-07-31T00:00:00Z',
      },
    } as never)

    const wrapper = renderWorkflow()
    await flushPromises()

    expect(wrapper.text()).toContain('项目工作流')

    await wrapper.findAll('button').find(button => button.text() === '保存')!.trigger('click')
    await flushPromises()
    expect(createWorkflowDefinition).toHaveBeenCalledWith(expect.objectContaining({
      project_id: 'project-1',
      template_id: 'free-canvas',
    }))

    await wrapper.findAll('button').find(button => button.text() === '运行工作流')!.trigger('click')
    await flushPromises()
    expect(createWorkflowRun).toHaveBeenCalledWith('flow-1', expect.objectContaining({
      name: '未命名流程',
      input_files: {},
    }))
    expect(getWorkflowRuns).toHaveBeenLastCalledWith(expect.objectContaining({
      project_id: 'project-1',
      workflow_definition_id: 'flow-1',
    }))
  })

  it('已保存流程列表隐藏归档项，并支持复制、归档和删除当前流程', async () => {
    vi.mocked(getWorkflowDefinitions).mockResolvedValue({
      data: {
        items: [
          {
            id: 'flow-active',
            user_id: 'user-1',
            name: '生产流程',
            description: null,
            template_id: 'free-canvas',
            nodes: [],
            edges: [],
            selected_tool_by_node: {},
            artifact_bindings_by_node: {},
            status: 'draft',
            created_at: '2026-07-31T00:00:00Z',
            updated_at: '2026-07-31T00:00:00Z',
          },
          {
            id: 'flow-archived',
            user_id: 'user-1',
            name: '归档流程',
            description: null,
            template_id: 'free-canvas',
            nodes: [],
            edges: [],
            selected_tool_by_node: {},
            artifact_bindings_by_node: {},
            status: 'archived',
            created_at: '2026-07-31T00:00:00Z',
            updated_at: '2026-07-31T00:00:00Z',
          },
        ],
        total: 2,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
    } as never)

    const wrapper = renderWorkflow()
    const workflowDefinitionsStore = useWorkflowDefinitionsStore()
    workflowDefinitionsStore.workflowDefinitions = (await getWorkflowDefinitions()).data.items
    await flushPromises()

    expect(wrapper.text()).toContain('生产流程')
    expect(wrapper.text()).not.toContain('归档流程')
    await wrapper.find('.select-option').trigger('click')
    await flushPromises()

    await wrapper.findAll('button').find(button => button.text() === '复制')!.trigger('click')
    await flushPromises()
    expect(createWorkflowDefinition).toHaveBeenLastCalledWith(expect.objectContaining({
      name: '未命名流程 副本',
      template_id: 'free-canvas',
    }))

    await wrapper.findAll('button').find(button => button.text() === '归档')!.trigger('click')
    await flushPromises()
    expect(updateWorkflowDefinition).toHaveBeenCalledWith('flow-1', { status: 'archived' })

    await wrapper.find('.select-option').trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '删除')!.trigger('click')
    await flushPromises()
    expect(deleteWorkflowDefinition).toHaveBeenCalledWith('flow-active')
  })

  it('Agent 草稿生成后保存为项目工作流草稿并导入画布', async () => {
    const wrapper = renderWorkflow()
    await flushPromises()

    await wrapper.find('.emit-agent-draft').trigger('click')
    await flushPromises()

    expect(createWorkflowDefinition).toHaveBeenLastCalledWith(expect.objectContaining({
      name: 'Agent Draft',
      description: 'Generated from agent',
      project_id: 'project-1',
      template_id: 'aidd-workflow-draft',
      selected_tool_by_node: { pocket_prediction: 'lvpocket' },
      status: 'draft',
    }))
  })
})
