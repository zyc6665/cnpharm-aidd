import { computed, ref, unref, watch, type Ref } from 'vue'
import type { Tool } from '@/types/models'

type MaybeRef<T> = T | Ref<T>

export interface WorkflowAvailableTool {
  id?: string
  slug: string
  name: string
  description?: string
}

export interface WorkflowNodeSelectedToolApi {
  getToolDetail: (toolId: string) => Promise<Tool>
}

export interface WorkflowNodeSelectedToolOptions {
  selectedToolSlug: MaybeRef<string | null | undefined>
  availableTools: MaybeRef<readonly WorkflowAvailableTool[] | undefined>
  api: WorkflowNodeSelectedToolApi
  onMissingTool?: () => void
}

export function useWorkflowNodeSelectedTool(options: WorkflowNodeSelectedToolOptions) {
  const selectedTool = ref<Tool | null>(null)
  const selectedToolLoading = ref(false)
  let detailRequestToken = 0

  const selectedToolSummary = computed(() => {
    const selectedToolSlug = unref(options.selectedToolSlug)
    if (!selectedToolSlug) {
      return null
    }

    return unref(options.availableTools)?.find(tool => tool.slug === selectedToolSlug) ?? null
  })

  watch(
    () => [unref(options.selectedToolSlug), selectedToolSummary.value?.id ?? null] as const,
    async ([selectedToolSlug, toolId]) => {
      const requestToken = ++detailRequestToken

      if (!selectedToolSlug || !toolId) {
        selectedTool.value = null
        selectedToolLoading.value = false
        options.onMissingTool?.()
        return
      }

      selectedTool.value = null
      selectedToolLoading.value = true
      try {
        const tool = await options.api.getToolDetail(toolId)
        if (requestToken === detailRequestToken) {
          selectedTool.value = tool
        }
      } finally {
        if (requestToken === detailRequestToken) {
          selectedToolLoading.value = false
        }
      }
    },
    { immediate: true }
  )

  return {
    selectedTool,
    selectedToolLoading,
    selectedToolSummary,
  }
}
