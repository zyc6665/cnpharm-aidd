import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { WorkflowTaskRef } from '@/workflow/artifact-types'
import { toWorkflowTaskRef } from '@/workflow/task-state'

interface WorkflowWorkbenchSession {
  sessionId: string
  activeGroupId: string | null
  selectedToolByGroup: Record<string, string>
  toolFormDrafts: Record<string, Record<string, unknown>>
  taskByTool: Record<string, WorkflowTaskRef>
  lastUpdatedAt: string
  ownerUserId?: string
}

function nowIsoString(): string {
  return new Date().toISOString()
}

function createWorkflowSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return `workflow-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function createInitialWorkflowSession(ownerUserId?: string): WorkflowWorkbenchSession {
  return {
    sessionId: createWorkflowSessionId(),
    activeGroupId: null,
    selectedToolByGroup: {},
    toolFormDrafts: {},
    taskByTool: {},
    lastUpdatedAt: nowIsoString(),
    ownerUserId
  }
}

export const useWorkflowStore = defineStore('workflow', () => {
  const initialSession = createInitialWorkflowSession()

  const sessionId = ref(initialSession.sessionId)
  const activeGroupId = ref<string | null>(initialSession.activeGroupId)
  const selectedToolByGroup = ref<Record<string, string>>(initialSession.selectedToolByGroup)
  const toolFormDrafts = ref<Record<string, Record<string, unknown>>>(initialSession.toolFormDrafts)
  const taskByTool = ref<Record<string, WorkflowTaskRef>>(initialSession.taskByTool)
  const lastUpdatedAt = ref(initialSession.lastUpdatedAt)
  const ownerUserId = ref<string | undefined>(initialSession.ownerUserId)

  const session = computed<WorkflowWorkbenchSession>(() => ({
    sessionId: sessionId.value,
    activeGroupId: activeGroupId.value,
    selectedToolByGroup: selectedToolByGroup.value,
    toolFormDrafts: toolFormDrafts.value,
    taskByTool: taskByTool.value,
    lastUpdatedAt: lastUpdatedAt.value,
    ownerUserId: ownerUserId.value
  }))

  function touchSession() {
    lastUpdatedAt.value = nowIsoString()
  }

  function resetSession(nextOwnerUserId?: string) {
    const nextSession = createInitialWorkflowSession(nextOwnerUserId)

    sessionId.value = nextSession.sessionId
    activeGroupId.value = nextSession.activeGroupId
    selectedToolByGroup.value = nextSession.selectedToolByGroup
    toolFormDrafts.value = nextSession.toolFormDrafts
    taskByTool.value = nextSession.taskByTool
    lastUpdatedAt.value = nextSession.lastUpdatedAt
    ownerUserId.value = nextSession.ownerUserId
  }

  function syncOwnerUserId(nextOwnerUserId?: string) {
    if (ownerUserId.value !== nextOwnerUserId) {
      resetSession(nextOwnerUserId)
    }
  }

  function setActiveGroup(groupId: string | null) {
    activeGroupId.value = groupId
    touchSession()
  }

  function selectTool(groupId: string, toolSlug: string) {
    selectedToolByGroup.value = {
      ...selectedToolByGroup.value,
      [groupId]: toolSlug
    }
    touchSession()
  }

  function setToolFormDraft(toolSlug: string, draft: Record<string, unknown>) {
    toolFormDrafts.value = {
      ...toolFormDrafts.value,
      [toolSlug]: draft
    }
    touchSession()
  }

  function clearToolFormDraft(toolSlug: string) {
    if (!toolFormDrafts.value[toolSlug]) {
      return
    }

    const nextDrafts = { ...toolFormDrafts.value }
    delete nextDrafts[toolSlug]
    toolFormDrafts.value = nextDrafts
    touchSession()
  }

  function recordTask(toolSlug: string, taskInput: WorkflowTaskRef) {
    taskByTool.value = {
      ...taskByTool.value,
      [toolSlug]: toWorkflowTaskRef(taskInput)
    }
    touchSession()
  }

  function clearTask(toolSlug: string) {
    if (!taskByTool.value[toolSlug]) {
      return
    }

    const nextTasks = { ...taskByTool.value }
    delete nextTasks[toolSlug]
    taskByTool.value = nextTasks
    touchSession()
  }

  return {
    sessionId,
    activeGroupId,
    selectedToolByGroup,
    toolFormDrafts,
    taskByTool,
    lastUpdatedAt,
    ownerUserId,
    session,
    resetSession,
    syncOwnerUserId,
    setActiveGroup,
    selectTool,
    setToolFormDraft,
    clearToolFormDraft,
    recordTask,
    clearTask
  }
}, {
  persist: {
    pick: [
      'sessionId',
      'activeGroupId',
      'selectedToolByGroup',
      'toolFormDrafts',
      'taskByTool',
      'lastUpdatedAt',
      'ownerUserId'
    ]
  }
})
