import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  cancelAiddAgentRun,
  createAiddAgentRun,
  createAiddWorkflowDraft,
  deleteAiddAgentRun,
  getAiddAgentRun,
  getAiddAgentRuns,
  syncAiddAgentRun
} from '@/api/agents'
import type {
  AiddAgentRun,
  AiddAgentRunCreateParams,
  AiddAgentRunStatus,
  AiddWorkflowDraft,
  PaginationParams
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
  const total = ref(0)
  let pollTimer: number | null = null

  const fetchRuns = async (params?: PaginationParams) => {
    loading.value = true
    try {
      const res = await getAiddAgentRuns(params)
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

  const syncRun = async (runId: string) => {
    const res = await syncAiddAgentRun(runId)
    currentRun.value = res.data
    const index = runs.value.findIndex(run => run.id === runId)
    if (index !== -1) {
      runs.value[index] = res.data
    }
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

  const clearPolling = () => {
    if (pollTimer !== null) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
  }

  const pollRunUntilTerminal = (runId: string, intervalMs = 5000) => {
    clearPolling()
    pollTimer = window.setInterval(async () => {
      const run = await syncRun(runId)
      if (isTerminalRunStatus(run.status)) {
        clearPolling()
      }
    }, intervalMs)
  }

  return {
    runs,
    currentRun,
    loading,
    drafting,
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
