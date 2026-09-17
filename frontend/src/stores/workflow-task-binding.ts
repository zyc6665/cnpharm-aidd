import { defineStore } from 'pinia'
import { ref } from 'vue'
import { normalizeRecord } from './workflow-session'
import type { WorkflowTaskRef } from '@/workflow/artifact-types'
import { toWorkflowTaskRef } from '@/workflow/task-state'

export const useWorkflowTaskBindingStore = defineStore('workflow-task-binding', () => {
  const taskByNode = ref<Record<string, WorkflowTaskRef>>({})
  const artifactBindingsByNode = ref<Record<string, Record<string, string>>>({})

  function normalizeShape() {
    taskByNode.value = normalizeRecord<WorkflowTaskRef>(taskByNode.value)
    artifactBindingsByNode.value = normalizeRecord<Record<string, string>>(
      artifactBindingsByNode.value,
    )
  }

  function reset() {
    taskByNode.value = {}
    artifactBindingsByNode.value = {}
  }

  function recordNodeTask(nodeId: string, taskInput: WorkflowTaskRef) {
    taskByNode.value = { ...taskByNode.value, [nodeId]: toWorkflowTaskRef(taskInput) }
  }

  function setNodeArtifactBinding(nodeId: string, field: string, artifactId: string) {
    artifactBindingsByNode.value = {
      ...artifactBindingsByNode.value,
      [nodeId]: {
        ...(artifactBindingsByNode.value[nodeId] ?? {}),
        [field]: artifactId,
      },
    }
  }

  function clearNodeTask(nodeId: string) {
    if (!taskByNode.value[nodeId]) return
    const next = { ...taskByNode.value }
    delete next[nodeId]
    taskByNode.value = next
  }

  function clearNodeTasks(nodeIds: string[]) {
    if (nodeIds.length === 0) return
    const next = { ...taskByNode.value }
    let changed = false
    for (const nodeId of nodeIds) {
      if (next[nodeId]) {
        delete next[nodeId]
        changed = true
      }
    }
    if (!changed) return
    taskByNode.value = next
  }

  function clearNodeArtifactBindings(nodeId: string) {
    if (!artifactBindingsByNode.value[nodeId]) return
    const next = { ...artifactBindingsByNode.value }
    delete next[nodeId]
    artifactBindingsByNode.value = next
  }

  return {
    taskByNode,
    artifactBindingsByNode,
    normalizeShape,
    reset,
    recordNodeTask,
    setNodeArtifactBinding,
    clearNodeTask,
    clearNodeTasks,
    clearNodeArtifactBindings,
  }
}, {
  persist: {
    pick: ['taskByNode', 'artifactBindingsByNode'],
  },
})
