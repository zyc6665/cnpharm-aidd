import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Task, TaskStatus, TaskCreateParams, TaskRunPreparationPreview } from '@/types/models'
import {
  getTaskList,
  getTaskCounts,
  getTaskDetail,
  createTask as apiCreateTask,
  prepareTaskRun as apiPrepareTaskRun,
  cancelTask as apiCancelTask,
  retryTask as apiRetryTask,
  deleteTask as apiDeleteTask,
  type TaskListParams
} from '@/api/tasks'
import type { TaskCountQueryParams, TaskViewCounts } from '@/domain/tasks/listing'
import { normalizeTaskSummaries, normalizeTaskSummary } from '@/utils/task-normalization'

const FULL_TASK_PAGE_SIZE = 100
const EMPTY_TASK_VIEW_COUNTS: TaskViewCounts = {
  all: 0,
  running: 0,
  history: 0,
  needs_attention: 0,
  recent_results: 0,
}

export const useTasksStore = defineStore('tasks', () => {
  // State
  const tasks = ref<Task[]>([])
  const currentTask = ref<Task | null>(null)
  const loading = ref(false)
  // 详情页自己的加载态：与列表的 `loading` 分开，避免详情页的实时刷新
  // 把列表页（或反过来）整块切成骨架屏。
  const detailLoading = ref(false)
  // 加载失败要能被页面看见：否则 500/断网会和"确实没有任务"长得一模一样
  const loadError = ref(false)
  const total = ref(0)
  const viewCounts = ref<TaskViewCounts>({ ...EMPTY_TASK_VIEW_COUNTS })
  let taskDetailRequestId = 0

  // Actions
  const fetchTasks = async (params?: TaskListParams) => {
    loading.value = true
    loadError.value = false
    try {
      const res = await getTaskList(params)
      tasks.value = normalizeTaskSummaries(res.data.items)
      total.value = res.data.total
      return res.data
    } catch (error) {
      loadError.value = true
      throw error
    } finally {
      loading.value = false
    }
  }

  const fetchAllTasks = async (
    params?: Pick<
      TaskListParams,
      'view' | 'tool_id' | 'keyword' | 'project_id' | 'created_from' | 'created_to'
    >
  ) => {
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

  const fetchTaskCounts = async (params?: TaskCountQueryParams) => {
    const res = await getTaskCounts(params)
    viewCounts.value = { ...EMPTY_TASK_VIEW_COUNTS, ...res.data }
    return viewCounts.value
  }

  const fetchTaskDetail = async (id: string) => {
    const requestId = ++taskDetailRequestId
    // 详情加载与列表加载是两个主体，共用一个 loading 会让「详情页收到一条
    // 进度事件」顺带把列表页也切成骨架屏。分开放，各自只影响自己。
    detailLoading.value = true
    try {
      const res = await getTaskDetail(id)
      if (requestId === taskDetailRequestId) {
        currentTask.value = res.data
      }
      return res.data
    } finally {
      if (requestId === taskDetailRequestId) {
        detailLoading.value = false
      }
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

  const prepareTaskRun = async (params: TaskCreateParams): Promise<TaskRunPreparationPreview> => {
    loading.value = true
    try {
      const res = await apiPrepareTaskRun(params)
      return res.data
    } finally {
      loading.value = false
    }
  }

  const cancelTask = async (id: string) => {
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
  }

  const retryTask = async (id: string) => {
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
  }

  const deleteTask = async (id: string) => {
    await apiDeleteTask(id)
    // 从列表中移除
    tasks.value = tasks.value.filter(t => t.id !== id)
    total.value = Math.max(total.value - 1, 0)
    if (currentTask.value?.id === id) {
      currentTask.value = null
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
    taskDetailRequestId += 1
    currentTask.value = null
    detailLoading.value = false
  }

  return {
    // State
    tasks,
    currentTask,
    loading,
    detailLoading,
    loadError,
    total,
    viewCounts,
    // Actions
    fetchTasks,
    fetchAllTasks,
    fetchTaskCounts,
    fetchTaskDetail,
    createTask,
    prepareTaskRun,
    cancelTask,
    retryTask,
    deleteTask,
    updateTaskProgress,
    clearCurrentTask
  }
})
