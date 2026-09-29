import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  type WorkflowRunListParams,
  cancelWorkflowRun,
  createWorkflowRun,
  getWorkflowRun,
  getWorkflowRuns,
  retryWorkflowRunNode as retryWorkflowRunNodeRequest,
  syncWorkflowRun,
} from '@/api/workflows'
import type { WorkflowRun, WorkflowRunCreateParams } from '@/types/models'
import type { WorkflowRunsPagination } from './workflow-session'

export const useWorkflowRunsStore = defineStore('workflow-runs', () => {
  const workflowRuns = ref<WorkflowRun[]>([])
  const workflowRunsPagination = ref<WorkflowRunsPagination>({
    total: 0,
    page: 1,
    pageSize: 20,
    totalPages: 0,
  })
  const activeWorkflowRun = ref<WorkflowRun | null>(null)
  const activeWorkflowRunId = ref<string | null>(null)
  const isLoadingWorkflowRuns = ref(false)
  const isLoadingMoreWorkflowRuns = ref(false)
  const isLoadingWorkflowRun = ref(false)
  const isRunningWorkflowDefinition = ref(false)
  const isSyncingWorkflowRun = ref(false)
  const isCancelingWorkflowRun = ref(false)
  const retryingWorkflowRunNodeId = ref<string | null>(null)
  let workflowRunRequestId = 0

  const hasMoreWorkflowRuns = computed(() => (
    workflowRunsPagination.value.page < workflowRunsPagination.value.totalPages
  ))

  function upsertWorkflowRun(run: WorkflowRun) {
    workflowRuns.value = [run, ...workflowRuns.value.filter((item) => item.id !== run.id)]
  }

  async function loadWorkflowRuns(
    params?: WorkflowRunListParams,
    options: { append?: boolean } = {},
  ) {
    if (options.append) {
      isLoadingMoreWorkflowRuns.value = true
    } else {
      isLoadingWorkflowRuns.value = true
    }
    try {
      const response = await getWorkflowRuns(params)
      const next = response.data.items
      workflowRuns.value = options.append
        ? [...workflowRuns.value, ...next.filter((item) => !workflowRuns.value.some((run) => run.id === item.id))]
        : next
      workflowRunsPagination.value = {
        total: response.data.total,
        page: response.data.page,
        pageSize: response.data.page_size,
        totalPages: response.data.total_pages,
      }
      return response.data
    } finally {
      if (options.append) {
        isLoadingMoreWorkflowRuns.value = false
      } else {
        isLoadingWorkflowRuns.value = false
      }
    }
  }

  async function runWorkflowDefinition(workflowDefinitionId: string, input: WorkflowRunCreateParams) {
    isRunningWorkflowDefinition.value = true
    try {
      const response = await createWorkflowRun(workflowDefinitionId, input)
      activeWorkflowRun.value = response.data
      activeWorkflowRunId.value = response.data.id
      upsertWorkflowRun(response.data)
      return response.data
    } finally {
      isRunningWorkflowDefinition.value = false
    }
  }

  async function loadWorkflowRun(runId: string) {
    const requestId = ++workflowRunRequestId
    isLoadingWorkflowRun.value = true
    try {
      const response = await getWorkflowRun(runId)
      if (requestId === workflowRunRequestId) {
        activeWorkflowRun.value = response.data
        activeWorkflowRunId.value = response.data.id
        upsertWorkflowRun(response.data)
      }
      return response.data
    } finally {
      if (requestId === workflowRunRequestId) {
        isLoadingWorkflowRun.value = false
      }
    }
  }

  async function syncActiveWorkflowRun(runId = activeWorkflowRunId.value) {
    if (!runId) {
      return null
    }
    isSyncingWorkflowRun.value = true
    try {
      const response = await syncWorkflowRun(runId)
      activeWorkflowRun.value = response.data
      activeWorkflowRunId.value = response.data.id
      upsertWorkflowRun(response.data)
      return response.data
    } finally {
      isSyncingWorkflowRun.value = false
    }
  }

  async function cancelActiveWorkflowRun(runId = activeWorkflowRunId.value) {
    if (!runId) {
      return null
    }
    isCancelingWorkflowRun.value = true
    try {
      const response = await cancelWorkflowRun(runId)
      activeWorkflowRun.value = response.data
      activeWorkflowRunId.value = response.data.id
      upsertWorkflowRun(response.data)
      return response.data
    } finally {
      isCancelingWorkflowRun.value = false
    }
  }

  async function retryWorkflowRunNode(runId: string, nodeId: string) {
    retryingWorkflowRunNodeId.value = nodeId
    try {
      const response = await retryWorkflowRunNodeRequest(runId, nodeId)
      activeWorkflowRun.value = response.data
      activeWorkflowRunId.value = response.data.id
      upsertWorkflowRun(response.data)
      return response.data
    } finally {
      retryingWorkflowRunNodeId.value = null
    }
  }

  function clearActiveWorkflowRun() {
    workflowRunRequestId += 1
    activeWorkflowRun.value = null
    activeWorkflowRunId.value = null
    isLoadingWorkflowRun.value = false
  }

  function clear() {
    workflowRuns.value = []
    workflowRunsPagination.value = { total: 0, page: 1, pageSize: 20, totalPages: 0 }
    clearActiveWorkflowRun()
  }

  function selectWorkflowRun(runId: string) {
    const run = workflowRuns.value.find((item) => item.id === runId)
    if (!run) {
      return false
    }
    activeWorkflowRun.value = run
    activeWorkflowRunId.value = run.id
    return true
  }

  return {
    workflowRuns,
    workflowRunsPagination,
    activeWorkflowRun,
    activeWorkflowRunId,
    isLoadingWorkflowRuns,
    isLoadingMoreWorkflowRuns,
    isLoadingWorkflowRun,
    isRunningWorkflowDefinition,
    isSyncingWorkflowRun,
    isCancelingWorkflowRun,
    retryingWorkflowRunNodeId,
    hasMoreWorkflowRuns,
    loadWorkflowRuns,
    runWorkflowDefinition,
    loadWorkflowRun,
    syncActiveWorkflowRun,
    cancelActiveWorkflowRun,
    retryWorkflowRunNode,
    clearActiveWorkflowRun,
    clear,
    selectWorkflowRun,
  }
})
