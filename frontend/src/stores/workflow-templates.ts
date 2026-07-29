import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  createWorkflowTemplate,
  deleteWorkflowTemplate,
  duplicateWorkflowTemplate,
  getWorkflowTemplate,
  getWorkflowTemplates,
  updateWorkflowTemplate,
} from '@/api/workflows'
import type {
  WorkflowDefinition,
  WorkflowTemplate,
  WorkflowTemplateCreateParams,
  WorkflowTemplateUpdateParams,
} from '@/types/models'
import { nowIsoString } from './workflow-session'

export const useWorkflowTemplatesStore = defineStore('workflow-templates', () => {
  const workflowTemplates = ref<WorkflowTemplate[]>([])
  const activeWorkflowTemplate = ref<WorkflowTemplate | null>(null)
  const activeWorkflowTemplateId = ref<string | null>(null)
  const isLoadingWorkflowTemplates = ref(false)
  const isSavingWorkflowTemplate = ref(false)

  async function loadWorkflowTemplates() {
    isLoadingWorkflowTemplates.value = true
    try {
      const response = await getWorkflowTemplates()
      workflowTemplates.value = response.data.items
      return response.data
    } finally {
      isLoadingWorkflowTemplates.value = false
    }
  }

  async function loadWorkflowTemplate(templateId: string) {
    const response = await getWorkflowTemplate(templateId)
    activeWorkflowTemplate.value = response.data
    activeWorkflowTemplateId.value = response.data.id
    return response.data
  }

  async function saveWorkflowTemplate(data: WorkflowTemplateCreateParams) {
    isSavingWorkflowTemplate.value = true
    try {
      const response = await createWorkflowTemplate(data)
      activeWorkflowTemplate.value = response.data
      activeWorkflowTemplateId.value = response.data.id
      workflowTemplates.value = [response.data, ...workflowTemplates.value]
      return response.data
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function updateSavedWorkflowTemplate(templateId: string, data: WorkflowTemplateUpdateParams) {
    isSavingWorkflowTemplate.value = true
    try {
      const response = await updateWorkflowTemplate(templateId, data)
      activeWorkflowTemplate.value = response.data
      activeWorkflowTemplateId.value = response.data.id
      workflowTemplates.value = workflowTemplates.value.map((template) => (
        template.id === response.data.id ? response.data : template
      ))
      return response.data
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function duplicateSavedWorkflowTemplate(templateId: string, name?: string) {
    isSavingWorkflowTemplate.value = true
    try {
      const response = await duplicateWorkflowTemplate(templateId, { name })
      activeWorkflowTemplate.value = response.data
      activeWorkflowTemplateId.value = response.data.id
      workflowTemplates.value = [response.data, ...workflowTemplates.value]
      return response.data
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function removeWorkflowTemplate(templateId: string) {
    isSavingWorkflowTemplate.value = true
    try {
      await deleteWorkflowTemplate(templateId)
      workflowTemplates.value = workflowTemplates.value.filter((template) => template.id !== templateId)
      if (activeWorkflowTemplateId.value === templateId) {
        clearActiveWorkflowTemplate()
      }
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  function setActiveWorkflowDefinition(
    definition: WorkflowDefinition,
    ownerUserId?: string,
    name = 'Untitled Workflow',
  ) {
    activeWorkflowTemplate.value = {
      id: activeWorkflowTemplateId.value ?? '',
      owner_id: ownerUserId ?? '',
      name,
      status: 'draft',
      definition,
      is_public: false,
      version: 1,
      created_at: nowIsoString(),
      updated_at: nowIsoString(),
    }
  }

  function clearActiveWorkflowTemplate() {
    activeWorkflowTemplate.value = null
    activeWorkflowTemplateId.value = null
  }

  return {
    workflowTemplates,
    activeWorkflowTemplate,
    activeWorkflowTemplateId,
    isLoadingWorkflowTemplates,
    isSavingWorkflowTemplate,
    loadWorkflowTemplates,
    loadWorkflowTemplate,
    saveWorkflowTemplate,
    updateSavedWorkflowTemplate,
    duplicateSavedWorkflowTemplate,
    removeWorkflowTemplate,
    setActiveWorkflowDefinition,
    clearActiveWorkflowTemplate,
  }
})
