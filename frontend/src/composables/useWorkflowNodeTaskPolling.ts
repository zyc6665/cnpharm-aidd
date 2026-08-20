import { getCurrentScope, onScopeDispose, unref, watch, type Ref } from 'vue'
import { getTaskDetail, isTaskTerminalStatus } from '@/api/tasks'
import type { WorkflowTaskRef } from '@/workflow/artifact-types'

type MaybeRef<T> = T | Ref<T>

export function useWorkflowNodeTaskPolling(input: {
  taskByNode: MaybeRef<Record<string, WorkflowTaskRef | null | undefined>>
  recordNodeTask: (nodeId: string, task: WorkflowTaskRef) => void
  refreshArtifacts?: () => void | Promise<unknown>
  intervalMs?: number
}) {
  const intervalMs = input.intervalMs ?? 5000
  const timers = new Map<string, number>()

  function stopNode(nodeId: string) {
    const timer = timers.get(nodeId)
    if (timer !== undefined) {
      window.clearTimeout(timer)
      timers.delete(nodeId)
    }
  }

  function stop() {
    for (const nodeId of timers.keys()) {
      stopNode(nodeId)
    }
  }

  function schedule(nodeId: string, taskId: string) {
    if (timers.has(nodeId)) {
      return
    }

    const poll = async () => {
      try {
        const response = await getTaskDetail(taskId)
        input.recordNodeTask(nodeId, response.data)

        if (isTaskTerminalStatus(response.data.status)) {
          stopNode(nodeId)
          if (response.data.status === 'success') {
            void input.refreshArtifacts?.()
          }
          return
        }
      } catch {
        // Keep polling through transient request failures so restored canvas state can recover.
      }

      timers.set(nodeId, window.setTimeout(poll, intervalMs))
    }

    timers.set(nodeId, window.setTimeout(poll, intervalMs))
  }

  const stopWatching = watch(
    () => unref(input.taskByNode),
    (taskByNode) => {
      const currentNodeIds = new Set(Object.keys(taskByNode ?? {}))

      for (const nodeId of Array.from(timers.keys())) {
        if (!currentNodeIds.has(nodeId)) {
          stopNode(nodeId)
        }
      }

      for (const [nodeId, task] of Object.entries(taskByNode ?? {})) {
        if (!task?.id || isTaskTerminalStatus(task.status)) {
          stopNode(nodeId)
          continue
        }

        schedule(nodeId, task.id)
      }
    },
    { deep: true, immediate: true }
  )

  function dispose() {
    stopWatching()
    stop()
  }

  if (getCurrentScope()) {
    onScopeDispose(dispose)
  }

  return {
    stop: dispose,
  }
}
