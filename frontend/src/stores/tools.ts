import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Tool, Category, Tag, RelatedTool, ToolView } from '@/types/models'
import {
  getToolList,
  getToolDetail,
  getCategories,
  getTags,
  favoriteTool,
  unfavoriteTool,
  getFavoriteTools,
  getCustomTools,
  getRelatedTools,
  getPopularTools,
  getRecentTools
} from '@/api/tools'

export const useToolsStore = defineStore('tools', () => {
  // State
  const tools = ref<Tool[]>([])
  const favoriteToolsList = ref<Tool[]>([])
  const customToolsList = ref<Tool[]>([])
  const relatedToolsList = ref<RelatedTool[]>([])
  const popularToolsList = ref<Tool[]>([])
  const recentToolsList = ref<Tool[]>([])
  const categories = ref<Category[]>([])
  const tags = ref<Tag[]>([])
  const currentTool = ref<Tool | null>(null)
  const currentView = ref<ToolView>('public')
  const loading = ref(false)
  const total = ref(0)
  const favoritesTotal = ref(0)
  const customTotal = ref(0)

  // Getters
  const currentToolsList = computed(() => {
    switch (currentView.value) {
      case 'favorite':
        return favoriteToolsList.value
      case 'custom':
        return customToolsList.value
      default:
        return tools.value
    }
  })

  const currentTotal = computed(() => {
    switch (currentView.value) {
      case 'favorite':
        return favoritesTotal.value
      case 'custom':
        return customTotal.value
      default:
        return total.value
    }
  })

  // Actions
  const setCurrentView = (view: ToolView) => {
    currentView.value = view
  }

  const fetchTools = async (params?: Record<string, unknown>) => {
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

  const fetchFavoriteTools = async (params?: Record<string, unknown>) => {
    loading.value = true
    try {
      const res = await getFavoriteTools(params)
      favoriteToolsList.value = res.data.items
      favoritesTotal.value = res.data.total
      return res.data
    } finally {
      loading.value = false
    }
  }

  const fetchCustomTools = async (params?: Record<string, unknown>) => {
    loading.value = true
    try {
      const res = await getCustomTools(params)
      customToolsList.value = res.data.items
      customTotal.value = res.data.total
      return res.data
    } finally {
      loading.value = false
    }
  }

  const fetchRelatedTools = async (toolId: number, limit?: number) => {
    try {
      const res = await getRelatedTools(toolId, limit)
      relatedToolsList.value = res.data
      return res.data
    } catch {
      relatedToolsList.value = []
      return []
    }
  }

  const fetchPopularTools = async (limit?: number) => {
    try {
      const res = await getPopularTools(limit)
      popularToolsList.value = res.data
      return res.data
    } catch {
      return []
    }
  }

  const fetchRecentTools = async (limit?: number) => {
    try {
      const res = await getRecentTools(limit)
      recentToolsList.value = res.data
      return res.data
    } catch {
      return []
    }
  }

  const fetchToolDetail = async (id: number) => {
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

  const toggleFavorite = async (toolId: number) => {
    const tool = tools.value.find(t => t.id === toolId)
      || favoriteToolsList.value.find(t => t.id === toolId)
      || currentTool.value
    if (!tool) return

    try {
      if (tool.is_favorited) {
        await unfavoriteTool(toolId)
        tool.is_favorited = false
        tool.favorite_count--
        // 从收藏列表移除
        const idx = favoriteToolsList.value.findIndex(t => t.id === toolId)
        if (idx > -1) {
          favoriteToolsList.value.splice(idx, 1)
          favoritesTotal.value--
        }
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
    relatedToolsList.value = []
  }

  return {
    // State
    tools,
    favoriteToolsList,
    customToolsList,
    relatedToolsList,
    popularToolsList,
    recentToolsList,
    categories,
    tags,
    currentTool,
    currentView,
    loading,
    total,
    favoritesTotal,
    customTotal,
    // Aliases
    favorites: favoriteToolsList,
    // Getters
    currentToolsList,
    currentTotal,
    // Actions
    setCurrentView,
    fetchTools,
    fetchFavoriteTools,
    fetchFavorites: fetchFavoriteTools,
    fetchCustomTools,
    fetchRelatedTools,
    fetchPopularTools,
    fetchRecentTools,
    fetchToolDetail,
    fetchCategories,
    fetchTags,
    toggleFavorite,
    clearCurrentTool
  }
})
