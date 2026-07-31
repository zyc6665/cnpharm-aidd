import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  approvePlanVersion,
  branchConversationMessage,
  createConversationMessage,
  getConversationMessages,
  getProjectConversations,
  getProjectResearchContext,
  rejectPlanVersion,
} from '@/api/conversations'
import type {
  AgentEvent,
  ApprovalContentBlock,
  ConversationMessage,
  ProjectConversation,
  ProjectResearchContext,
} from '@/types/conversations'

export const useProjectConversationStore = defineStore('project-conversation', () => {
  const project = ref<ProjectResearchContext | null>(null)
  const conversations = ref<ProjectConversation[]>([])
  const activeConversationId = ref<string | null>(null)
  const messages = ref<ConversationMessage[]>([])
  const events = ref<AgentEvent[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastSequence = computed(() => events.value[events.value.length - 1]?.sequence ?? 0)
  const canRun = computed(() => ['owner', 'runner'].includes(project.value?.membership.role || ''))
  const activeRunId = computed(() => {
    for (let index = events.value.length - 1; index >= 0; index -= 1) {
      const runId = events.value[index]?.payload.run_id
      if (typeof runId === 'string') return runId
    }
    for (const message of messages.value) {
      const approval = message.content.find(block => block.type === 'approval_ref') as ApprovalContentBlock | undefined
      if (approval?.run_id) return approval.run_id
    }
    return null
  })

  function applyEvent(event: AgentEvent) {
    if (event.sequence <= lastSequence.value) return
    events.value.push(event)
  }

  function resetEvents() {
    events.value = []
  }

  async function loadProject(projectId: string, preferredConversationId?: string) {
    loading.value = true
    error.value = null
    try {
      const [projectResponse, conversationResponse] = await Promise.all([
        getProjectResearchContext(projectId, { retry: 2, silent: true }),
        getProjectConversations(projectId, { retry: 2, silent: true }),
      ])
      project.value = projectResponse.data
      conversations.value = conversationResponse.data.items
      activeConversationId.value = preferredConversationId || conversations.value[0]?.id || null
      if (activeConversationId.value) await loadMessages(activeConversationId.value)
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '项目研究数据加载失败'
    } finally {
      loading.value = false
    }
  }

  async function loadMessages(conversationId: string) {
    activeConversationId.value = conversationId
    const response = await getConversationMessages(conversationId, undefined, { retry: 2, silent: true })
    messages.value = response.data.items
  }

  async function sendMessage(text: string) {
    if (!activeConversationId.value) return null
    const response = await createConversationMessage(
      activeConversationId.value,
      [{ type: 'text', text }],
      messages.value[messages.value.length - 1]?.branch_id,
    )
    messages.value.push(response.data)
    return response.data
  }

  async function branchFromMessage(message: ConversationMessage, text: string) {
    const response = await branchConversationMessage(message.id, {
      content: [{ type: 'text', text }],
      title: text.slice(0, 80),
    })
    messages.value.push(response.data.message)
    return response.data
  }

  async function decidePlan(planId: string, decision: 'approve' | 'reject', comment?: string) {
    const response = decision === 'approve'
      ? await approvePlanVersion(planId, comment)
      : await rejectPlanVersion(planId, comment)
    for (const message of messages.value) {
      for (const block of message.content) {
        if (block.type === 'approval_ref' && block.plan_id === planId) block.status = response.data.status
      }
    }
    return response.data
  }

  return {
    project,
    conversations,
    activeConversationId,
    messages,
    events,
    loading,
    error,
    lastSequence,
    canRun,
    activeRunId,
    applyEvent,
    resetEvents,
    loadProject,
    loadMessages,
    sendMessage,
    branchFromMessage,
    decidePlan,
  }
})
