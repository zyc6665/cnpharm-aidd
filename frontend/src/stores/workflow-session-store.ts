import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  createInitialWorkflowSession,
  nowIsoString,
} from './workflow-session'

export const useWorkflowSessionStore = defineStore('workflow-session', () => {
  const initialSession = createInitialWorkflowSession()
  const sessionId = ref(initialSession.sessionId)
  const templateId = ref(initialSession.templateId)
  const lastUpdatedAt = ref(initialSession.lastUpdatedAt)
  const ownerUserId = ref<string | undefined>(initialSession.ownerUserId)

  function touch() {
    lastUpdatedAt.value = nowIsoString()
  }

  function normalize() {
    if (typeof templateId.value !== 'string' || !templateId.value) {
      templateId.value = 'aidd-template'
    }
  }

  function reset(nextOwnerUserId?: string) {
    const next = createInitialWorkflowSession(nextOwnerUserId)
    sessionId.value = next.sessionId
    templateId.value = next.templateId
    lastUpdatedAt.value = next.lastUpdatedAt
    ownerUserId.value = next.ownerUserId
  }

  function setTemplate(nextTemplateId: string) {
    if (templateId.value === nextTemplateId) {
      return false
    }

    templateId.value = nextTemplateId
    touch()
    return true
  }

  return {
    sessionId,
    templateId,
    lastUpdatedAt,
    ownerUserId,
    touch,
    normalize,
    reset,
    setTemplate,
  }
}, {
  persist: {
    pick: ['sessionId', 'templateId', 'lastUpdatedAt', 'ownerUserId'],
  },
})
