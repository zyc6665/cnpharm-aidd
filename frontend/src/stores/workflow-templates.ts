import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { PaginatedResponse, WorkflowDefinition } from '@/types/models'
import { nowIsoString } from './workflow-session'

interface WorkflowTemplateFacade {
  id: string
  owner_id: string
  name: string
  description?: string | null
  status: 'draft' | 'published' | string
  definition: WorkflowDefinition
  is_public: boolean
  version: number
  created_at: string
  updated_at: string
}

interface WorkflowTemplateCreateParams {
  name: string
  description?: string | null
  definition: WorkflowDefinition
  is_public?: boolean
}

type WorkflowTemplateUpdateParams = Partial<WorkflowTemplateCreateParams> & {
  status?: string
}

export const useWorkflowTemplatesStore = defineStore('workflow-templates', () => {
  const workflowTemplates = ref<WorkflowTemplateFacade[]>([])
  const activeWorkflowTemplate = ref<WorkflowTemplateFacade | null>(null)
  const activeWorkflowTemplateId = ref<string | null>(null)
  const isLoadingWorkflowTemplates = ref(false)
  const isSavingWorkflowTemplate = ref(false)

  async function loadWorkflowTemplates(): Promise<PaginatedResponse<WorkflowTemplateFacade>> {
    isLoadingWorkflowTemplates.value = true
    try {
      workflowTemplates.value = []
      return { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 }
    } finally {
      isLoadingWorkflowTemplates.value = false
    }
  }

  async function loadWorkflowTemplate(templateId: string) {
    const template = workflowTemplates.value.find(item => item.id === templateId)
      ?? (activeWorkflowTemplateId.value === templateId ? activeWorkflowTemplate.value : null)
    if (!template) {
      throw new Error('Workflow template compatibility state not found')
    }
    activeWorkflowTemplate.value = template
    activeWorkflowTemplateId.value = template.id
    return template
  }

  async function saveWorkflowTemplate(data: WorkflowTemplateCreateParams) {
    isSavingWorkflowTemplate.value = true
    try {
      const template = createLocalTemplate(data)
      activeWorkflowTemplate.value = template
      activeWorkflowTemplateId.value = template.id
      workflowTemplates.value = [template, ...workflowTemplates.value]
      return template
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function updateSavedWorkflowTemplate(templateId: string, data: WorkflowTemplateUpdateParams) {
    isSavingWorkflowTemplate.value = true
    try {
      const current = workflowTemplates.value.find(template => template.id === templateId)
        ?? activeWorkflowTemplate.value
      if (!current) {
        throw new Error('Workflow template compatibility state not found')
      }
      const template: WorkflowTemplateFacade = {
        ...current,
        name: data.name ?? current.name,
        description: data.description ?? current.description,
        definition: data.definition ?? current.definition,
        is_public: data.is_public ?? current.is_public,
        status: data.status ?? current.status,
        version: current.version + 1,
        updated_at: nowIsoString(),
      }
      activeWorkflowTemplate.value = template
      activeWorkflowTemplateId.value = template.id
      workflowTemplates.value = workflowTemplates.value.map(item => (
        item.id === template.id ? template : item
      ))
      return template
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function duplicateSavedWorkflowTemplate(templateId: string, name?: string) {
    isSavingWorkflowTemplate.value = true
    try {
      const current = workflowTemplates.value.find(template => template.id === templateId)
        ?? activeWorkflowTemplate.value
      if (!current) {
        throw new Error('Workflow template compatibility state not found')
      }
      const template = createLocalTemplate({
        name: name ?? `${current.name} Copy`,
        description: current.description,
        definition: current.definition,
        is_public: false,
      })
      activeWorkflowTemplate.value = template
      activeWorkflowTemplateId.value = template.id
      workflowTemplates.value = [template, ...workflowTemplates.value]
      return template
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function removeWorkflowTemplate(templateId: string) {
    isSavingWorkflowTemplate.value = true
    try {
      workflowTemplates.value = workflowTemplates.value.filter(template => template.id !== templateId)
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
    activeWorkflowTemplate.value = createLocalTemplate(
      { name, definition, is_public: false },
      activeWorkflowTemplateId.value ?? '',
      ownerUserId,
    )
  }

  function clearActiveWorkflowTemplate() {
    activeWorkflowTemplate.value = null
    activeWorkflowTemplateId.value = null
  }

  function createLocalTemplate(
    data: WorkflowTemplateCreateParams,
    id = `local-workflow-${Date.now()}`,
    ownerUserId = '',
  ): WorkflowTemplateFacade {
    const now = nowIsoString()
    return {
      id,
      owner_id: ownerUserId,
      name: data.name,
      description: data.description ?? null,
      status: 'draft',
      definition: data.definition,
      is_public: data.is_public ?? false,
      version: 1,
      created_at: now,
      updated_at: now,
    }
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
