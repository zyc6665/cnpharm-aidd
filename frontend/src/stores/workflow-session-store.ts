import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  createInitialWorkflowSession,
  nowIsoString,
} from './workflow-session'

export const useWorkflowSessionStore = defineStore('workflow-session', () => {
  const initialSession = createInitialWorkflowSession()
  const sessionId = ref(initialSession.sessionId)
  const canvasPresetId = ref(initialSession.canvasPresetId)
  const lastUpdatedAt = ref(initialSession.lastUpdatedAt)
  const ownerUserId = ref<string | undefined>(initialSession.ownerUserId)

  function touch() {
    lastUpdatedAt.value = nowIsoString()
  }

  function normalize() {
    if (typeof canvasPresetId.value !== 'string' || !canvasPresetId.value) {
      canvasPresetId.value = 'free-canvas'
    }
  }

  function reset(nextOwnerUserId?: string) {
    const next = createInitialWorkflowSession(nextOwnerUserId)
    sessionId.value = next.sessionId
    canvasPresetId.value = next.canvasPresetId
    lastUpdatedAt.value = next.lastUpdatedAt
    ownerUserId.value = next.ownerUserId
  }

  function setCanvasPreset(nextCanvasPresetId: string) {
    if (canvasPresetId.value === nextCanvasPresetId) {
      return false
    }

    canvasPresetId.value = nextCanvasPresetId
    touch()
    return true
  }

  return {
    sessionId,
    canvasPresetId,
    lastUpdatedAt,
    ownerUserId,
    touch,
    normalize,
    reset,
    setCanvasPreset,
  }
}, {
  persist: {
    pick: ['sessionId', 'canvasPresetId', 'lastUpdatedAt', 'ownerUserId'],
  },
})
