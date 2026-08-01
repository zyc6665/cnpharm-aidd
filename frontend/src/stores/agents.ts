import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  type AiddAgentRunListParams,
  cancelAiddAgentRun,
  createAiddAgentRun,
  createAiddWorkflowDraft,
  deleteAiddAgentRun,
  getAiddAgentRun,
  getAiddAgentRuns,
  syncAiddAgentRun
} from '@/api/agents'
import type { RequestOptions } from '@/api/request'
import type {
  AiddAgentRun,
  AiddAgentRunCreateParams,
  AiddAgentRunStatus,
  AiddWorkflowDraft
} from '@/types/models'

const TERMINAL_AGENT_STATUSES: readonly AiddAgentRunStatus[] = ['success', 'failure', 'canceled']

function isTerminalRunStatus(status: AiddAgentRunStatus): boolean {
  return TERMINAL_AGENT_STATUSES.includes(status)
}

export const useAgentsStore = defineStore('agents', () => {
  const runs = ref<AiddAgentRun[]>([])
  const currentRun = ref<AiddAgentRun | null>(null)
  const loading = ref(false)
  const drafting = ref(false)
  const pollError = ref<string | null>(null)
  const pollingSuspended = ref(false)
  const total = ref(0)
  let pollTimer: number | null = null
  let pollInFlight = false
  let pollFailureCount = 0

  const fetchRuns = async (params?: AiddAgentRunListParams, options?: RequestOptions) => {
    loading.value = true
    try {
      const res = await getAiddAgentRuns(params, options)
      runs.value = res.data.items
      total.value = res.data.total
      if (!currentRun.value) {
        currentRun.value = res.data.items[0] ?? null
      }
      return res.data
    } finally {
      loading.value = false
    }
  }

  const fetchRun = async (runId: string) => {
    const res = await getAiddAgentRun(runId)
    currentRun.value = res.data
    const index = runs.value.findIndex(run => run.id === runId)
    if (index !== -1) {
      runs.value[index] = res.data
    }
    return res.data
  }

  const createRun = async (params: AiddAgentRunCreateParams) => {
    loading.value = true
    try {
      const res = await createAiddAgentRun(params)
      currentRun.value = res.data
      runs.value.unshift(res.data)
      total.value += 1
      return res.data
    } finally {
      loading.value = false
    }
  }

  const createWorkflowDraft = async (
    params: AiddAgentRunCreateParams
  ): Promise<AiddWorkflowDraft> => {
    drafting.value = true
    try {
      const res = await createAiddWorkflowDraft(params)
      return res.data
    } finally {
      drafting.value = false
    }
  }

  const markPollingHealthy = () => {
    pollFailureCount = 0
    pollError.value = null
    pollingSuspended.value = false
  }

  const syncRun = async (runId: string, options?: RequestOptions) => {
    const res = await syncAiddAgentRun(runId, options)
    currentRun.value = res.data
    const index = runs.value.findIndex(run => run.id === runId)
    if (index !== -1) {
      runs.value[index] = res.data
    }
    markPollingHealthy()
    return res.data
  }

  const cancelRun = async (runId: string) => {
    const res = await cancelAiddAgentRun(runId)
    currentRun.value = res.data
    const index = runs.value.findIndex(run => run.id === runId)
    if (index !== -1) {
      runs.value[index] = res.data
    }
    return res.data
  }

  const deleteRun = async (runId: string, cascade = false) => {
    const res = await deleteAiddAgentRun(runId, cascade)
    runs.value = runs.value.filter(run => run.id !== runId)
    total.value = Math.max(0, total.value - 1)
    if (currentRun.value?.id === runId) {
      clearPolling()
      currentRun.value = runs.value[0] ?? null
    }
    return res.data
  }

  const stopPollingTimer = () => {
    if (pollTimer !== null) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
  }

  const clearPolling = () => {
    stopPollingTimer()
    pollInFlight = false
    markPollingHealthy()
  }

  const recordPollingFailure = (error: unknown) => {
    pollFailureCount += 1
    pollError.value = error instanceof Error ? error.message : 'Agent run status sync failed'
    if (pollFailureCount >= 3) {
      pollingSuspended.value = true
      stopPollingTimer()
    }
  }

  const pollRunUntilTerminal = (runId: string, intervalMs = 5000) => {
    clearPolling()
    pollTimer = window.setInterval(async () => {
      if (pollInFlight) {
        return
      }
      pollInFlight = true
      try {
        const run = await syncRun(runId, { silent: true, retry: 1 })
        if (isTerminalRunStatus(run.status)) {
          clearPolling()
        }
      } catch (error) {
        recordPollingFailure(error)
      } finally {
        pollInFlight = false
      }
    }, intervalMs)
  }

  return {
    runs,
    currentRun,
    loading,
    drafting,
    pollError,
    pollingSuspended,
    total,
    fetchRuns,
    fetchRun,
    createRun,
    createWorkflowDraft,
    syncRun,
    cancelRun,
    deleteRun,
    clearPolling,
    pollRunUntilTerminal
  }
})
