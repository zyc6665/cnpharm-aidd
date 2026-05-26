import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Tool, Category, Tag, ToolView } from '@/types/models'
import {
  getToolList,
  getToolDetail,
  getCategories,
  getTags,
  favoriteTool,
  unfavoriteTool,
  type ToolListParams
} from '@/api/tools'

export const useToolsStore = defineStore('tools', () => {
  const tools = ref<Tool[]>([])
  const categories = ref<Category[]>([])
  const tags = ref<Tag[]>([])
  const currentTool = ref<Tool | null>(null)
  const currentView = ref<ToolView>('public')
  const loading = ref(false)
  const total = ref(0)

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
    loading.value = true
    try {
      const res = await getToolDetail(id)
      currentTool.value = res.data
      return res.data
    } finally {
      loading.value = false
    }
  }

  const fetchCategories = async () => {
    try {
      const res = await getCategories()
      categories.value = res.data
      return res.data
    } catch {
      return []
    }
  }

  const fetchTags = async () => {
    try {
      const res = await getTags()
      tags.value = res.data
      return res.data
    } catch {
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
    currentTool.value = null
  }

  return {
    tools,
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
    fetchCategories,
    fetchTags,
    toggleFavorite,
    clearCurrentTool
  }
})
