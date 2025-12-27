import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Tool, Category, Tag, ToolView, ToolProviderType } from '@/types/models'
import {
  getToolList,
  getMyToolList,
  getToolDetail,
  getCategories,
  getTags,
  favoriteTool,
  unfavoriteTool,
  submitToolReview,
  adminReviewTool,
  adminGetPendingReviews,
  type ToolListParams,
  type MyToolListParams
} from '@/api/tools'

export const useToolsStore = defineStore('tools', () => {
  // State
  const tools = ref<Tool[]>([])
  const myTools = ref<Tool[]>([])
  const pendingReviewTools = ref<Tool[]>([])
  const categories = ref<Category[]>([])
  const tags = ref<Tag[]>([])
  const currentTool = ref<Tool | null>(null)
  const currentView = ref<ToolView>('public')
  const loading = ref(false)
  const total = ref(0)
  const myToolsTotal = ref(0)
  const pendingReviewTotal = ref(0)

  // Getters
  const currentToolsList = computed(() => tools.value)
  const currentTotal = computed(() => total.value)
  const platformTools = computed(() => tools.value.filter(t => t.provider_type === 'platform'))
  const communityTools = computed(() => tools.value.filter(t => t.provider_type === 'user'))

  // Actions
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

  // 获取我的工具列表
  const fetchMyTools = async (params?: MyToolListParams) => {
    loading.value = true
    try {
      const res = await getMyToolList(params)
      myTools.value = res.data.items
      myToolsTotal.value = res.data.total
      return res.data
    } finally {
      loading.value = false
    }
  }

  // 获取待审核工具列表（管理员）
  const fetchPendingReviewTools = async (params?: { page?: number; page_size?: number }) => {
    loading.value = true
    try {
      const res = await adminGetPendingReviews(params)
      pendingReviewTools.value = res.data.items
      pendingReviewTotal.value = res.data.total
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

  // 提交工具审核
  const submitReview = async (toolId: string) => {
    try {
      const res = await submitToolReview(toolId)
      // 更新本地状态
      const tool = myTools.value.find(t => t.id === toolId)
      if (tool) {
        tool.review_status = res.data.review_status as Tool['review_status']
      }
      return res.data
    } catch {
      throw new Error('提交审核失败')
    }
  }

  // 审核工具（管理员）
  const reviewTool = async (toolId: string, action: 'approve' | 'reject', rejectReason?: string) => {
    try {
      const res = await adminReviewTool(toolId, {
        action,
        reject_reason: rejectReason
      })
      // 从待审核列表中移除
      pendingReviewTools.value = pendingReviewTools.value.filter(t => t.id !== toolId)
      pendingReviewTotal.value--
      return res.data
    } catch {
      throw new Error('审核失败')
    }
  }

  const clearCurrentTool = () => {
    currentTool.value = null
  }

  return {
    // State
    tools,
    myTools,
    pendingReviewTools,
    categories,
    tags,
    currentTool,
    currentView,
    loading,
    total,
    myToolsTotal,
    pendingReviewTotal,
    // Getters
    currentToolsList,
    currentTotal,
    platformTools,
    communityTools,
    // Actions
    setCurrentView,
    fetchTools,
    fetchMyTools,
    fetchPendingReviewTools,
    fetchToolDetail,
    fetchCategories,
    fetchTags,
    toggleFavorite,
    submitReview,
    reviewTool,
    clearCurrentTool
  }
})
