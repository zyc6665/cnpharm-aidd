import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  createWorkflowDefinition,
  deleteWorkflowDefinition,
  getWorkflowDefinition,
  getWorkflowDefinitions,
  updateWorkflowDefinition,
  type WorkflowDefinition,
  type WorkflowDefinitionPayload,
  type WorkflowDefinitionUpdatePayload
} from '@/api/workflows'

export const useWorkflowDefinitionsStore = defineStore('workflow-definitions', () => {
  const workflowDefinitions = ref<WorkflowDefinition[]>([])
  const currentWorkflowDefinition = ref<WorkflowDefinition | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const total = ref(0)

  async function fetchWorkflowDefinitions(params?: { page?: number; page_size?: number }) {
    loading.value = true
    try {
      const res = await getWorkflowDefinitions(params)
      workflowDefinitions.value = res.data.items
      total.value = res.data.total
      return res.data
    } catch {
      workflowDefinitions.value = []
      total.value = 0
      return {
        items: [],
        total: 0,
        page: params?.page ?? 1,
        page_size: params?.page_size ?? 20,
        total_pages: 0
      }
    } finally {
      loading.value = false
    }
  }

  async function loadWorkflowDefinition(id: string) {
    loading.value = true
    try {
      const res = await getWorkflowDefinition(id)
      currentWorkflowDefinition.value = res.data
      return res.data
    } finally {
      loading.value = false
    }
  }

  async function saveWorkflowDefinition(
    payload: WorkflowDefinitionPayload,
    workflowId?: string | null
  ) {
    saving.value = true
    try {
      const res = workflowId
        ? await updateWorkflowDefinition(workflowId, payload as WorkflowDefinitionUpdatePayload)
        : await createWorkflowDefinition(payload)

      currentWorkflowDefinition.value = res.data
      await fetchWorkflowDefinitions({ page: 1, page_size: 100 })
      return res.data
    } finally {
      saving.value = false
    }
  }

  async function removeWorkflowDefinition(id: string) {
    await deleteWorkflowDefinition(id)
    workflowDefinitions.value = workflowDefinitions.value.filter(item => item.id !== id)
    total.value = Math.max(total.value - 1, 0)
    if (currentWorkflowDefinition.value?.id === id) {
      currentWorkflowDefinition.value = null
    }
  }

  function clearCurrentWorkflowDefinition() {
    currentWorkflowDefinition.value = null
  }

  return {
    workflowDefinitions,
    currentWorkflowDefinition,
    loading,
    saving,
    total,
    fetchWorkflowDefinitions,
    loadWorkflowDefinition,
    saveWorkflowDefinition,
    removeWorkflowDefinition,
    clearCurrentWorkflowDefinition
  }
})
