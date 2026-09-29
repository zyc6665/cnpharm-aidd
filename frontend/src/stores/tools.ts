import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Tool, Category, Tag, ToolView, ToolOptionSummary, WorkbenchGroup } from '@/types/models'
import {
  getToolList,
  getToolDetail,
  getCategories,
  getTags,
  getWorkbenchGroups,
  getWorkflowToolOptions,
  favoriteTool,
  unfavoriteTool,
  type ToolListParams
} from '@/api/tools'

export const useToolsStore = defineStore('tools', () => {
  const tools = ref<Tool[]>([])
  const workflowToolOptions = ref<ToolOptionSummary[]>([])
  const workbenchGroups = ref<WorkbenchGroup[]>([])
  const categories = ref<Category[]>([])
  const tags = ref<Tag[]>([])
  const currentTool = ref<Tool | null>(null)
  const currentView = ref<ToolView>('public')
  const loading = ref(false)
  const total = ref(0)
  let currentToolRequestId = 0

  const currentToolsList = computed(() => tools.value)
  const currentTotal = computed(() => total.value)

  const setCurrentView = (view: ToolView) => {
    currentView.value = view
  }

  const fetchTools = async (params?: ToolListParams) => {
    loading.value = true
    try {
      const res = await getToolList(params)
      tools.value = res.data.items
      total.value = res.data.total
      return res.data
    } finally {
      loading.value = false
    }
  }

  const fetchToolDetail = async (id: string) => {
    const requestId = ++currentToolRequestId
    loading.value = true
    try {
      const res = await getToolDetail(id)
      if (requestId === currentToolRequestId) {
        currentTool.value = res.data
      }
      return res.data
    } finally {
      if (requestId === currentToolRequestId) {
        loading.value = false
      }
    }
  }

  const fetchWorkflowTools = async () => {
    try {
      const res = await getWorkflowToolOptions()
      workflowToolOptions.value = res.data
      return res.data
    } catch {
      workflowToolOptions.value = []
      return []
    }
  }

  const fetchWorkbenchGroups = async () => {
    try {
      const res = await getWorkbenchGroups()
      workbenchGroups.value = res.data
      return res.data
    } catch {
      workbenchGroups.value = []
      return []
    }
  }

  const fetchCategories = async () => {
    try {
      const res = await getCategories()
      categories.value = res.data
      return res.data
    } catch {
      categories.value = []
      return []
    }
  }

  const fetchTags = async () => {
    try {
      const res = await getTags()
      tags.value = res.data
      return res.data
    } catch {
      tags.value = []
      return []
    }
  }

  const toggleFavorite = async (toolId: string) => {
    const tool = tools.value.find(t => t.id === toolId) || currentTool.value
    if (!tool) return

    try {
      if (tool.is_favorited) {
        await unfavoriteTool(toolId)
        tool.is_favorited = false
        tool.favorite_count--
      } else {
        await favoriteTool(toolId)
        tool.is_favorited = true
        tool.favorite_count++
      }
    } catch {
      // 错误已在请求层处理
    }
  }

  const clearCurrentTool = () => {
    currentToolRequestId += 1
    currentTool.value = null
    loading.value = false
  }

  return {
    tools,
    workflowToolOptions,
    workbenchGroups,
    categories,
    tags,
    currentTool,
    currentView,
    loading,
    total,
    currentToolsList,
    currentTotal,
    setCurrentView,
    fetchTools,
    fetchToolDetail,
    fetchWorkflowTools,
    fetchWorkbenchGroups,
    fetchCategories,
    fetchTags,
    toggleFavorite,
    clearCurrentTool
  }
})
