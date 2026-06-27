import { defineStore } from 'pinia'
import { ref } from 'vue'
import { normalizeRecord } from './workflow-session'

export const useWorkflowFormDraftStore = defineStore('workflow-form-draft', () => {
  const selectedToolByGroup = ref<Record<string, string>>({})
  const selectedToolByNode = ref<Record<string, string>>({})
  const toolFormDrafts = ref<Record<string, Record<string, unknown>>>({})
  const nodeFormDrafts = ref<Record<string, Record<string, unknown>>>({})

  function normalizeShape() {
    selectedToolByGroup.value = normalizeRecord<string>(selectedToolByGroup.value)
    selectedToolByNode.value = normalizeRecord<string>(selectedToolByNode.value)
    toolFormDrafts.value = normalizeRecord<Record<string, unknown>>(toolFormDrafts.value)
    nodeFormDrafts.value = normalizeRecord<Record<string, unknown>>(nodeFormDrafts.value)
  }

  function reset() {
    selectedToolByGroup.value = {}
    selectedToolByNode.value = {}
    toolFormDrafts.value = {}
    nodeFormDrafts.value = {}
  }

  function selectTool(groupId: string, toolSlug: string) {
    selectedToolByGroup.value = { ...selectedToolByGroup.value, [groupId]: toolSlug }
  }

  function selectNodeTool(nodeId: string, toolSlug: string) {
    selectedToolByNode.value = { ...selectedToolByNode.value, [nodeId]: toolSlug }
  }

  function removeNodeSelection(nodeId: string) {
    const next = { ...selectedToolByNode.value }
    delete next[nodeId]
    selectedToolByNode.value = next
  }

  function setToolFormDraft(toolSlug: string, draft: Record<string, unknown>) {
    toolFormDrafts.value = { ...toolFormDrafts.value, [toolSlug]: draft }
  }

  function setNodeFormDraft(nodeId: string, draft: Record<string, unknown>) {
    nodeFormDrafts.value = { ...nodeFormDrafts.value, [nodeId]: draft }
  }

  function clearToolFormDraft(toolSlug: string) {
    if (!toolFormDrafts.value[toolSlug]) return
    const next = { ...toolFormDrafts.value }
    delete next[toolSlug]
    toolFormDrafts.value = next
  }

  function clearNodeFormDraft(nodeId: string) {
    if (!nodeFormDrafts.value[nodeId]) return
    const next = { ...nodeFormDrafts.value }
    delete next[nodeId]
    nodeFormDrafts.value = next
  }

  return {
    selectedToolByGroup,
    selectedToolByNode,
    toolFormDrafts,
    nodeFormDrafts,
    normalizeShape,
    reset,
    selectTool,
    selectNodeTool,
    removeNodeSelection,
    setToolFormDraft,
    setNodeFormDraft,
    clearToolFormDraft,
    clearNodeFormDraft,
  }
}, {
  persist: {
    pick: ['selectedToolByGroup', 'selectedToolByNode', 'toolFormDrafts', 'nodeFormDrafts'],
  },
})
