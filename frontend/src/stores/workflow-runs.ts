import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  type WorkflowRunListParams,
  createWorkflowRun,
  getWorkflowRun,
  getWorkflowRuns,
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
    isLoadingWorkflowRun.value = true
    try {
      const response = await getWorkflowRun(runId)
      activeWorkflowRun.value = response.data
      activeWorkflowRunId.value = response.data.id
      upsertWorkflowRun(response.data)
      return response.data
    } finally {
      isLoadingWorkflowRun.value = false
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

  function clearActiveWorkflowRun() {
    activeWorkflowRun.value = null
    activeWorkflowRunId.value = null
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
    hasMoreWorkflowRuns,
    loadWorkflowRuns,
    runWorkflowDefinition,
    loadWorkflowRun,
    syncActiveWorkflowRun,
    clearActiveWorkflowRun,
    clear,
    selectWorkflowRun,
  }
})
