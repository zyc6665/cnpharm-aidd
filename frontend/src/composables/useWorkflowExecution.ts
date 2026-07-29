import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { getTaskDetail, isTaskTerminalStatus } from '@/api/tasks'
import { getToolDetail } from '@/api/tools'
import type { ArtifactFile, Tool, ToolSchema } from '@/types/models'
import type { UploadedToolFile } from '@/views/tools/detail-schema'
import {
  buildTaskSubmissionPayload,
  flattenToolInputSchema,
  isFileSchemaProperty,
} from '@/views/tools/detail-schema'
import { toWorkflowTaskRef } from '@/workflow/task-state'
import type { WorkflowTaskRef } from '@/workflow/artifact-types'
import { sortArtifactsByCreatedAtDesc } from '@/utils/artifact-sorting'
import { useArtifactsStore, useTasksStore, useWorkflowStore } from '@/stores'
import type { useWorkflowCanvas } from './useWorkflowCanvas'

type WorkflowStore = ReturnType<typeof useWorkflowStore>
type TasksStore = ReturnType<typeof useTasksStore>
type ArtifactsStore = ReturnType<typeof useArtifactsStore>
type WorkflowCanvasState = ReturnType<typeof useWorkflowCanvas>

export function useWorkflowExecution(input: {
  workflowStore: WorkflowStore
  tasksStore: TasksStore
  artifactsStore: ArtifactsStore
  editableTemplate: WorkflowCanvasState['editableTemplate']
  readyToolNodeIds: WorkflowCanvasState['readyToolNodeIds']
  resolveToolForNode: WorkflowCanvasState['resolveToolForNode']
  resolveDownstreamNodeIds: WorkflowCanvasState['resolveDownstreamNodeIds']
  formatKey: WorkflowCanvasState['formatKey']
}) {
  const {
    workflowStore,
    tasksStore,
    artifactsStore,
    editableTemplate,
    readyToolNodeIds,
    resolveToolForNode,
    resolveDownstreamNodeIds,
    formatKey,
  } = input

  const runningWorkflow = ref(false)

  async function handleNodeTaskSubmitted() {
    await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
  }

  async function handleRunNode(nodeId: string) {
    workflowStore.setActiveNode(nodeId)
    const node = editableTemplate.value.nodes.find((item) => item.id === nodeId)
    if (!node) {
      return null
    }

    const tool = resolveToolForNode(nodeId)
    if (!tool) {
      message.warning('当前节点缺少可运行工具')
      return null
    }

    try {
      const preparedPayload = await prepareWorkflowNodeTaskPayload(nodeId, tool.id)
      const task = await tasksStore.createTask({
        name: formatKey(node.titleKey),
        tool_id: tool.id,
        params: preparedPayload.params,
        file_ids: preparedPayload.fileIds.length > 0 ? preparedPayload.fileIds : undefined,
        priority: 'normal',
      })

      workflowStore.recordNodeTask(nodeId, toWorkflowTaskRef(task))
      message.success('节点任务已提交')
      if (isTaskTerminalStatus(task.status)) {
        await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
        return toWorkflowTaskRef(task)
      }

      return await pollNodeTaskUntilTerminal(nodeId, task.id)
    } catch {
      return null
    }
  }

  async function prepareWorkflowNodeTaskPayload(nodeId: string, toolId: string) {
    const response = await getToolDetail(toolId)
    const tool = response.data
    const flattenedSchema = flattenToolInputSchema(resolveToolInputSchema(tool)) ?? {
      type: 'object',
      properties: {},
      required: [],
    }
    const workflowParams = {
      workflow_template_id: editableTemplate.value.id,
      workflow_node_id: nodeId,
      workflow_node_type: editableTemplate.value.nodes.find((node) => node.id === nodeId)?.type,
    }
    const draft = {
      ...(workflowStore.nodeFormDrafts[nodeId] ?? {}),
    }
    const uploadedFiles = resolveWorkflowNodeUploadedFiles(nodeId, flattenedSchema, draft)

    const payload = buildTaskSubmissionPayload({
      flattenedSchema,
      formState: draft,
      uploadedFiles,
      executorType: resolveToolExecutorType(tool),
    })

    return {
      params: {
        ...payload.params,
        ...workflowParams,
      },
      fileIds: payload.fileIds,
    }
  }

  function resolveToolInputSchema(tool: Tool): ToolSchema | undefined {
    const config = tool.current_version?.config
    if (config && typeof config === 'object' && 'input_schema' in config) {
      return config.input_schema as ToolSchema
    }

    return undefined
  }

  function resolveToolExecutorType(tool: Tool): string | undefined {
    const config = tool.current_version?.config
    if (config && typeof config === 'object' && 'type' in config && typeof config.type === 'string') {
      return config.type
    }

    return undefined
  }

  function resolveWorkflowNodeUploadedFiles(
    nodeId: string,
    flattenedSchema: ToolSchema,
    draft: Record<string, unknown>,
  ): Record<string, UploadedToolFile | undefined> {
    const uploadedFiles: Record<string, UploadedToolFile | undefined> = {}
    const recommendedArtifacts = resolveRecommendedArtifactsForNode(nodeId)

    for (const [key, prop] of Object.entries(flattenedSchema.properties)) {
      if (!isFileSchemaProperty(prop)) {
        continue
      }

      const draftedArtifact = findArtifactByUnknownId(draft[key])
      const artifact = draftedArtifact ?? recommendedArtifacts.shift()
      if (!artifact) {
        continue
      }

      draft[key] = artifact.id
      uploadedFiles[key] = {
        fileId: artifact.id,
        filename: artifact.filename,
        downloadUrl: artifact.download_url,
      }
    }

    return uploadedFiles
  }

  function resolveRecommendedArtifactsForNode(nodeId: string): ArtifactFile[] {
    return sortArtifactsByCreatedAtDesc(editableTemplate.value.edges
      .filter((edge) => edge.target === nodeId)
      .map((edge) => workflowStore.taskByNode[edge.source])
      .filter((task): task is WorkflowTaskRef => task?.status === 'success')
      .flatMap((task) => artifactsStore.items.filter((artifact) => artifact.task_id === task.id)))
  }

  function findArtifactByUnknownId(value: unknown): ArtifactFile | null {
    if (typeof value !== 'string' && typeof value !== 'number') {
      return null
    }

    return artifactsStore.items.find((artifact) => artifact.id === String(value)) ?? null
  }

  async function pollNodeTaskUntilTerminal(nodeId: string, taskId: string) {
    for (;;) {
      await new Promise((resolve) => window.setTimeout(resolve, 3000))
      const response = await getTaskDetail(taskId)
      const taskRef = toWorkflowTaskRef(response.data)
      workflowStore.recordNodeTask(nodeId, taskRef)

      if (isTaskTerminalStatus(response.data.status)) {
        if (response.data.status === 'success') {
          await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
        }
        return taskRef
      }
    }
  }

  async function handleRunReadyNodes() {
    if (readyToolNodeIds.value.length === 0) {
      message.info('当前没有可运行节点')
      return
    }

    await runWorkflowUntilBlocked()
  }

  async function runWorkflowUntilBlocked() {
    runningWorkflow.value = true
    try {
      for (;;) {
        const orderedNodeIds = readyToolNodeIds.value.filter((nodeId) => {
          const task = workflowStore.taskByNode[nodeId]
          return !task || task.status === 'failure' || task.status === 'canceled'
        })

        if (orderedNodeIds.length === 0) {
          message.info('当前没有更多可运行节点')
          return
        }

        const task = await handleRunNode(orderedNodeIds[0]!)
        if (!task || task.status !== 'success') {
          message.warning('工作流已暂停，请检查当前节点任务结果')
          return
        }
      }
    } finally {
      runningWorkflow.value = false
    }
  }

  async function runDownstreamFrom(nodeId: string) {
    const rerunNodeIds = resolveDownstreamNodeIds(nodeId).filter((candidateNodeId) => {
      return editableTemplate.value.nodes.some((node) => node.id === candidateNodeId && node.type === 'tool')
    })

    workflowStore.clearNodeTasks(rerunNodeIds)
    workflowStore.clearActiveWorkflowRun()
    workflowStore.setActiveNode(nodeId)

    const task = await handleRunNode(nodeId)
    if (task?.status === 'success') {
      await handleRunReadyNodes()
    }
  }

  return {
    runningWorkflow,
    handleNodeTaskSubmitted,
    handleRunNode,
    handleRunReadyNodes,
    runDownstreamFrom,
  }
}
