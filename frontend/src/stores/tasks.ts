import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Task, TaskStatus, TaskCreateParams } from '@/types/models'
import { getTaskList, getTaskDetail, createTask as apiCreateTask, cancelTask as apiCancelTask, retryTask as apiRetryTask, deleteTask as apiDeleteTask } from '@/api/tasks'
import { normalizeTaskSummaries, normalizeTaskSummary } from '@/utils/task-normalization'

const FULL_TASK_PAGE_SIZE = 100

export const useTasksStore = defineStore('tasks', () => {
  // State
  const tasks = ref<Task[]>([])
  const currentTask = ref<Task | null>(null)
  const loading = ref(false)
  const total = ref(0)

  // Actions
  const fetchTasks = async (params?: { status?: TaskStatus; tool_id?: string; keyword?: string; page?: number; page_size?: number }) => {
    loading.value = true
    try {
      const res = await getTaskList(params)
      tasks.value = normalizeTaskSummaries(res.data.items)
      total.value = res.data.total
      return res.data
    } finally {
      loading.value = false
    }
  }

  const fetchAllTasks = async (params?: { tool_id?: string; keyword?: string }) => {
    loading.value = true
    try {
      const firstPage = await getTaskList({
        ...params,
        page: 1,
        page_size: FULL_TASK_PAGE_SIZE
      })
      const allItems = [...firstPage.data.items]
      const pageCount = Math.ceil(firstPage.data.total / FULL_TASK_PAGE_SIZE)

      for (let page = 2; page <= pageCount; page += 1) {
        const res = await getTaskList({
          ...params,
          page,
          page_size: FULL_TASK_PAGE_SIZE
        })
        allItems.push(...res.data.items)
      }

      tasks.value = normalizeTaskSummaries(allItems)
      total.value = firstPage.data.total
      return {
        ...firstPage.data,
        items: tasks.value,
        page: 1,
        page_size: allItems.length
      }
    } finally {
      loading.value = false
    }
  }

  const fetchTaskDetail = async (id: string) => {
    loading.value = true
    try {
      const res = await getTaskDetail(id)
      currentTask.value = res.data
      return res.data
    } finally {
      loading.value = false
    }
  }

  const createTask = async (params: TaskCreateParams) => {
    loading.value = true
    try {
      const res = await apiCreateTask(params)
      // 添加到列表开头
      tasks.value.unshift(normalizeTaskSummary(res.data))
      total.value++
      return res.data
    } finally {
      loading.value = false
    }
  }

  const cancelTask = async (id: string) => {
    try {
      const res = await apiCancelTask(id)
      // 更新列表中的任务状态
      const index = tasks.value.findIndex(t => t.id === id)
      if (index !== -1) {
        tasks.value[index] = normalizeTaskSummary(res.data)
      }
      if (currentTask.value?.id === id) {
        currentTask.value = res.data
      }
      return res.data
    } catch {
      // 错误已在请求层处理
    }
  }

  const retryTask = async (id: string) => {
    try {
      const res = await apiRetryTask(id)
      // 更新列表中的任务状态
      const index = tasks.value.findIndex(t => t.id === id)
      if (index !== -1) {
        tasks.value[index] = normalizeTaskSummary(res.data)
      }
      if (currentTask.value?.id === id) {
        currentTask.value = res.data
      }
      return res.data
    } catch {
      // 错误已在请求层处理
    }
  }

  const deleteTask = async (id: string) => {
    try {
      await apiDeleteTask(id)
      // 从列表中移除
      tasks.value = tasks.value.filter(t => t.id !== id)
      total.value--
      if (currentTask.value?.id === id) {
        currentTask.value = null
      }
    } catch {
      // 错误已在请求层处理
    }
  }

  const updateTaskProgress = (id: string, progress: number, status?: TaskStatus) => {
    const task = tasks.value.find(t => t.id === id)
    if (task) {
      task.progress = progress
      if (status) {
        task.status = status
      }
    }
    if (currentTask.value?.id === id) {
      currentTask.value.progress = progress
      if (status) {
        currentTask.value.status = status
      }
    }
  }

  const clearCurrentTask = () => {
    currentTask.value = null
  }

  return {
    // State
    tasks,
    currentTask,
    loading,
    total,
    // Actions
    fetchTasks,
    fetchAllTasks,
    fetchTaskDetail,
    createTask,
    cancelTask,
    retryTask,
    deleteTask,
    updateTaskProgress,
    clearCurrentTask
  }
})
