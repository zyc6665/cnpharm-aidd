import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ResearchView from './Research.vue'
import {
  approvePlanVersion,
  branchConversationMessage,
  getConversationMessages,
  getProjectConversations,
  getProjectResearchContext,
  rejectPlanVersion,
  startProjectAgentRun,
} from '@/api/conversations'
import { cancelAiddAgentRun } from '@/api/agents'
import { useProjectConversationStore } from '@/stores/project-conversation'

const push = vi.fn()
vi.mock('vue-router', async importOriginal => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ params: { projectId: 'project-1', conversationId: 'conversation-1' } }),
    useRouter: () => ({ push }),
  }
})
vi.mock('@/api/conversations', () => ({
  approvePlanVersion: vi.fn(),
  branchConversationMessage: vi.fn(),
  createConversationMessage: vi.fn(),
  getConversationMessages: vi.fn(),
  getProjectConversations: vi.fn(),
  getProjectResearchContext: vi.fn(),
  rejectPlanVersion: vi.fn(),
  startProjectAgentRun: vi.fn(),
}))
vi.mock('@/api/agents', () => ({ cancelAiddAgentRun: vi.fn() }))
vi.mock('@/composables/useAgentEventStream', () => ({
  useAgentEventStream: () => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    connected: { value: false },
    reconnecting: { value: false },
    error: { value: null },
  }),
}))

const approvalBlock = {
  type: 'approval_ref',
  plan_id: 'plan-1',
  run_id: 'run-1',
  tool: 'LVpocket',
  parameters: { receptor: 'target.pdb', threshold: 0.5 },
  resources: { accelerator: 'NVIDIA GPU', gpu_count: 1 },
  estimated_duration_seconds: 180,
  network_access: false,
}

function renderResearch() {
  return mount(ResearchView, {
    global: {
      plugins: [createPinia()],
      stubs: {
        RouterLink: { template: '<a><slot /></a>' },
        AButton: { template: '<button :disabled="$attrs.disabled"><slot /></button>' },
        ATextarea: { template: '<textarea />' },
        AInput: { template: '<input />' },
        AEmpty: true,
        ASkeleton: true,
        ATag: { template: '<span><slot /></span>' },
        AProgress: true,
        ATooltip: { template: '<span><slot /></span>' },
      },
    },
  })
}

describe('ResearchView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getProjectResearchContext).mockResolvedValue({
      data: { id: 'project-1', name: '口袋研究', goal: '识别可成药口袋', membership: { role: 'viewer' } },
    } as never)
    vi.mocked(getProjectConversations).mockResolvedValue({
      data: { items: [{ id: 'conversation-1', project_id: 'project-1', title: '首次分析', status: 'active' }] },
    } as never)
    vi.mocked(getConversationMessages).mockResolvedValue({
      data: {
        items: [{
          id: 'message-1', conversation_id: 'conversation-1', branch_id: 'branch-1', role: 'assistant',
          content: [{ type: 'text', text: '已生成执行计划' }, approvalBlock], plain_text: '已生成执行计划', sequence: 1,
        }],
      },
    } as never)
    vi.mocked(cancelAiddAgentRun).mockResolvedValue({ data: { id: 'run-1' } } as never)
    vi.mocked(startProjectAgentRun).mockResolvedValue({ data: { id: 'run-new' } } as never)
    vi.mocked(branchConversationMessage).mockResolvedValue({
      data: {
        branch: { id: 'branch-2', forked_from_message_id: 'message-1' },
        message: {
          id: 'message-branch', conversation_id: 'conversation-1', branch_id: 'branch-2', role: 'user',
          content: [{ type: 'text', text: '分析 target.pdb' }], plain_text: '分析 target.pdb', sequence: 1,
        },
      },
    } as never)
  })

  it('展示会话、消息和项目检查器三栏及完整审批信息', async () => {
    const wrapper = renderResearch()
    await flushPromises()

    expect(wrapper.find('[data-testid="conversation-sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="message-timeline"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="project-inspector"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('LVpocket')
    expect(wrapper.text()).toContain('target.pdb')
    expect(wrapper.text()).toContain('NVIDIA GPU')
    expect(wrapper.text()).toContain('约 3 分钟')
    expect(wrapper.text()).toContain('不访问网络')
    expect(wrapper.get('[data-testid="approve-plan"]').attributes('disabled')).toBeDefined()
  })

  it('提供停止、重新生成、编辑并分支和失败重试操作', async () => {
    vi.mocked(getProjectResearchContext).mockResolvedValue({
      data: { id: 'project-1', name: '口袋研究', goal: '识别可成药口袋', membership: { role: 'runner' } },
    } as never)
    vi.mocked(getConversationMessages).mockResolvedValue({
      data: {
        items: [{
          id: 'message-1', conversation_id: 'conversation-1', branch_id: 'branch-1', role: 'user',
          content: [{ type: 'text', text: '分析 target.pdb' }], plain_text: '分析 target.pdb', sequence: 1,
        }, {
          id: 'message-2', conversation_id: 'conversation-1', branch_id: 'branch-1', role: 'assistant',
          content: [approvalBlock], plain_text: '等待审批', sequence: 2,
        }],
      },
    } as never)
    const wrapper = renderResearch()
    await flushPromises()
    useProjectConversationStore().applyEvent({
      id: 'failed-1', sequence: 1, event_type: 'execution_failed', payload: { run_id: 'run-1' },
    })
    await wrapper.vm.$nextTick()

    await wrapper.get('[data-testid="stop-run"]').trigger('click')
    await wrapper.get('[data-testid="regenerate-run"]').trigger('click')
    await wrapper.get('[data-testid="branch-message"]').trigger('click')
    await wrapper.get('textarea').setValue('分析 target.pdb 的 B 链')
    await wrapper.get('textarea').trigger('keydown.enter')
    await wrapper.get('[data-testid="retry-run"]').trigger('click')

    expect(cancelAiddAgentRun).toHaveBeenCalled()
    expect(startProjectAgentRun).toHaveBeenCalledTimes(3)
    expect(branchConversationMessage).toHaveBeenCalledWith('message-1', expect.any(Object))
    expect(wrapper.text()).toContain('失败后可重试')
    expect(approvePlanVersion).not.toHaveBeenCalled()
    expect(rejectPlanVersion).not.toHaveBeenCalled()
  })
})
