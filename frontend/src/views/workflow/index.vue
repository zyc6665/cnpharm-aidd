<template>
  <div class="workflow-page">
    <div class="workflow-shell workflow-deck">
      <AppPageHeader :title="t('workflow.title')" :subtitle="t('workflow.subtitle')" align="center" />

      <a-tabs v-model:activeKey="activeMode" class="workflow-mode-tabs">
        <a-tab-pane key="manual" :tab="t('workflow.mode.manual')">
          <div class="workflow-definition-bar">
            <a-input
              v-model:value="workflowName"
              class="workflow-name-input"
              placeholder="Workflow name"
            />
            <a-select
              v-model:value="selectedSavedWorkflowId"
              class="workflow-load-select"
              allow-clear
              placeholder="Saved workflows"
              :loading="workflowDefinitionsStore.loading"
              :options="savedWorkflowOptions"
            />
            <a-space size="small" wrap>
              <a-button
                type="primary"
                :loading="workflowDefinitionsStore.saving"
                @click="handleSaveWorkflow"
              >
                保存
              </a-button>
              <a-button
                :disabled="!selectedSavedWorkflowId"
                :loading="workflowDefinitionsStore.loading"
                @click="handleLoadWorkflow"
              >
                加载
              </a-button>
              <a-button
                :disabled="readyToolNodeIds.length === 0"
                :loading="runningWorkflow"
                @click="handleRunReadyNodes"
              >
                运行可执行节点
              </a-button>
            </a-space>
          </div>

          <div class="workflow-template-toolbar">
            <a-input
              v-model:value="workflowTemplateName"
              class="workflow-name-input"
              :placeholder="t('workflow.templates.namePlaceholder')"
            />
            <a-select
              class="workflow-load-select"
              :value="workflowStore.activeWorkflowTemplateId"
              :placeholder="t('workflow.templates.loadPlaceholder')"
              :options="workflowTemplateOptions"
              :loading="workflowStore.isLoadingWorkflowTemplates"
              allow-clear
              @change="handleTemplateSelect"
            />
            <a-space size="small" wrap>
              <a-button @click="handleNewWorkflowTemplate">
                {{ t('workflow.templates.new') }}
              </a-button>
              <a-button
                type="primary"
                :loading="workflowStore.isSavingWorkflowTemplate"
                @click="handleSaveWorkflowTemplate"
              >
                {{ t('workflow.templates.save') }}
              </a-button>
              <a-button
                :disabled="!workflowStore.activeWorkflowTemplateId"
                :loading="workflowStore.isSavingWorkflowTemplate"
                @click="handleDuplicateWorkflowTemplate"
              >
                {{ t('workflow.templates.duplicate') }}
              </a-button>
              <a-popconfirm
                :title="t('workflow.templates.deleteConfirm')"
                :ok-text="t('common.delete')"
                :cancel-text="t('common.cancel')"
                placement="bottomRight"
                @confirm="handleDeleteWorkflowTemplate"
              >
                <a-button
                  danger
                  :disabled="!workflowStore.activeWorkflowTemplateId"
                  :loading="workflowStore.isSavingWorkflowTemplate"
                >
                  {{ t('workflow.templates.delete') }}
                </a-button>
              </a-popconfirm>
              <a-button
                :disabled="!workflowStore.activeWorkflowTemplateId && !workflowTemplateName.trim()"
                :loading="workflowStore.isRunningWorkflowTemplate"
                @click="handleRunWorkflowTemplate"
              >
                {{ t('workflow.templates.run') }}
              </a-button>
            </a-space>
          </div>

          <div v-if="workflowInputRequirements.length > 0" class="workflow-run-input-panel">
            <div class="run-input-header">
              <span>{{ t('workflow.templates.requiredInputs') }}</span>
              <a-button
                size="small"
                :disabled="artifactsStore.loading || artifactsStore.items.length === 0"
                @click="autofillWorkflowInputSelections"
              >
                {{ t('workflow.templates.autoFillInputs') }}
              </a-button>
            </div>
            <div class="run-input-grid">
              <label
                v-for="semanticType in workflowInputRequirements"
                :key="semanticType"
                class="run-input-field"
              >
                <span>{{ semanticType }}</span>
                <a-select
                  :value="workflowRunInputSelections[semanticType]"
                  :options="getArtifactOptionsForSemanticType(semanticType)"
                  :placeholder="t('workflow.templates.selectInputArtifact')"
                  :loading="artifactsStore.loading"
                  allow-clear
                  show-search
                  option-filter-prop="label"
                  @change="handleWorkflowInputSelect(semanticType, $event)"
                />
              </label>
            </div>
          </div>

          <WorkflowRunHistoryPanel
            v-if="userStore.isLoggedIn"
            :runs="workflowStore.workflowRuns"
            :active-run-id="workflowStore.activeWorkflowRunId"
            :loading="workflowStore.isLoadingWorkflowRuns"
            :has-more="workflowStore.hasMoreWorkflowRuns"
            :loading-more="workflowStore.isLoadingMoreWorkflowRuns"
            @select="handleWorkflowRunSelect"
            @refresh="handleRefreshWorkflowRuns"
            @load-more="handleLoadMoreWorkflowRuns"
          />

          <WorkflowRunStatusPanel
            v-if="workflowStore.activeWorkflowRun"
            :run="workflowStore.activeWorkflowRun"
            :syncing="workflowStore.isSyncingWorkflowRun || workflowStore.isLoadingWorkflowRun"
            @sync="handleSyncWorkflowRun"
          />

          <section class="workflow-preflight-region">
            <WorkflowPreflightPanel
              :preflight="workflowPreflight"
              :running="runningWorkflow"
              @run-ready-nodes="handleRunReadyNodes"
              @select-node="workflowStore.setActiveNode"
            />
          </section>

          <div class="workflow-template-layout">
            <aside class="template-step-rail">
              <div class="template-selector">
                <span class="rail-kicker">Workflow template</span>
                <a-select
                  :value="workflowStore.templateId"
                  class="template-select"
                  :options="templateOptions"
                  @change="handleTemplateChange"
                />
              </div>

              <div class="workflow-status-summary">
                <div class="status-summary-item is-ready">
                  <span>可运行</span>
                  <strong>{{ readyNodeCount }}</strong>
                </div>
                <div class="status-summary-item is-blocked">
                  <span>阻塞</span>
                  <strong>{{ blockedNodeCount }}</strong>
                </div>
                <div class="status-summary-item is-running">
                  <span>运行中</span>
                  <strong>{{ runningNodeCount }}</strong>
                </div>
                <div class="status-summary-item is-completed">
                  <span>完成</span>
                  <strong>{{ completedNodeCount }}</strong>
                </div>
                <div class="status-summary-item is-failed">
                  <span>失败</span>
                  <strong>{{ failedNodeCount }}</strong>
                </div>
              </div>

              <div class="template-node-list">
                <button
                  v-for="node in editableTemplate.nodes"
                  :key="node.id"
                  type="button"
                  class="template-node-item"
                  :class="{ 'is-active': node.id === activeNode?.id }"
                  @click="workflowStore.setActiveNode(node.id)"
                >
                  <span class="node-item-title">{{ formatKey(node.titleKey) }}</span>
                  <span class="node-item-reason">{{ resolveNodeStatusReason(node.id) }}</span>
                  <WorkflowNodeStatusBadge :status="nodeStatuses[node.id] ?? 'idle'" />
                </button>
              </div>

              <div class="workflow-sidebar-tool-library">
                <div class="sidebar-tool-library-header">
                  <span class="rail-kicker">工具库</span>
                  <a-input-search
                    v-model:value="sidebarToolSearchKeyword"
                    placeholder="搜索工具"
                    allow-clear
                  />
                </div>
                <div class="sidebar-tool-list">
                  <button
                    v-for="tool in filteredSidebarToolOptions"
                    :key="tool.slug"
                    type="button"
                    class="sidebar-tool-item"
                    @click="handleAddToolNode(tool.slug)"
                  >
                    <span class="sidebar-tool-name">{{ tool.name || tool.slug }}</span>
                    <span v-if="tool.description" class="sidebar-tool-desc">{{ tool.description }}</span>
                    <span class="sidebar-tool-action">添加节点</span>
                  </button>
                  <a-empty
                    v-if="filteredSidebarToolOptions.length === 0"
                    class="sidebar-tool-empty"
                    description="暂无工具"
                  />
                </div>
              </div>
            </aside>

            <WorkflowTemplateCanvas
              :template="editableTemplate"
              :active-node-id="activeNode?.id ?? null"
              :node-statuses="nodeStatuses"
              :node-positions="workflowStore.nodePositionById"
              @select-node="workflowStore.setActiveNode"
              @move-node="workflowStore.moveNode"
              @add-tool-node="handleAddToolNode"
              @delete-node="handleDeleteNode"
            />

            <WorkflowNodeInspector
              :node="activeNode"
              :template="editableTemplate"
              :artifacts="artifactsStore.items"
              :task-by-node="workflowStore.taskByNode"
              :available-tools="availableWorkflowTools"
              :status="activeNode ? nodeStatuses[activeNode.id] : 'idle'"
              :selected-tool-slug="activeNode ? selectedToolByActiveNode : null"
              :task="activeNode ? workflowStore.taskByNode[activeNode.id] ?? null : null"
              @select-tool="handleNodeToolSelect"
              @add-edge="handleAddEdge"
              @delete-edge="handleDeleteEdge"
              @run-node="handleRunNode"
              @task-submitted="handleNodeTaskSubmitted"
            />
          </div>

          <section class="workflow-results-region">
            <WorkflowResultsReportPanel
              :workflow-name="workflowName"
              :rows="workflowReportRows"
            />
          </section>
        </a-tab-pane>
        <a-tab-pane key="agent" :tab="t('workflow.mode.agent')">
          <AiddAgentPanel />
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AiddAgentPanel from '@/components/workflow/AiddAgentPanel.vue'
  import WorkflowNodeInspector from '@/components/workflow/WorkflowNodeInspector.vue'
  import WorkflowPreflightPanel from '@/components/workflow/WorkflowPreflightPanel.vue'
  import WorkflowResultsReportPanel from '@/components/workflow/WorkflowResultsReportPanel.vue'
  import WorkflowRunHistoryPanel from '@/components/workflow/WorkflowRunHistoryPanel.vue'
  import WorkflowRunStatusPanel from '@/components/workflow/WorkflowRunStatusPanel.vue'
  import WorkflowNodeStatusBadge from '@/components/workflow/WorkflowNodeStatusBadge.vue'
  import WorkflowTemplateCanvas from '@/components/workflow/WorkflowTemplateCanvas.vue'
  import {
    useArtifactsStore,
    useTasksStore,
    useToolsStore,
    useUserStore,
    useWorkflowDefinitionsStore,
    useWorkflowStore
  } from '@/stores'
  import type { WorkflowDefinitionPayload } from '@/api/workflows'
  import { getTaskDetail, isTaskTerminalStatus } from '@/api/tasks'
  import { getToolDetail } from '@/api/tools'
  import {
    resolveReadyToolNodeIds,
    resolveWorkflowExecutionOrder,
    validateWorkflowDefinition,
    validateWorkflowExecutionOrder
  } from '@/workflow/template-runner'
  import { buildWorkflowPreflight } from '@/workflow/preflight'
  import {
    buildWorkflowInputFileMap,
    extractWorkflowInputRequirements,
    findLatestArtifactForSemanticType
  } from '@/workflow/workflow-definitions'
  import { shouldAutoSyncWorkflowRun } from '@/workflow/workflow-runs'
  import { toWorkflowTaskRef } from '@/workflow/task-state'
  import { resolveWorkflowCanvasNodeStatus } from '@/workflow/template-state'
  import {
    buildTaskSubmissionPayload,
    flattenToolInputSchema,
    isFileSchemaProperty,
    type UploadedToolFile
  } from '@/views/tools/detail-schema'
  import {
    AIDD_WORKFLOW_TEMPLATE,
    WORKFLOW_TEMPLATES,
    getWorkflowTemplateById
  } from '@/workflow/templates'
  import type { WorkflowArtifactSemanticType, WorkflowTaskRef } from '@/workflow/artifact-types'
  import type { WorkflowReportRow } from '@/workflow/report'
  import type {
    ArtifactFile,
    Tool,
    ToolSchema,
    WorkflowDefinition
  } from '@/types/models'

  const { t } = useI18n()
  const artifactsStore = useArtifactsStore()
  const tasksStore = useTasksStore()
  const toolsStore = useToolsStore()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()
  const workflowDefinitionsStore = useWorkflowDefinitionsStore()
  workflowStore.normalizeSessionShape()

  type WorkflowMode = 'manual' | 'agent'

  const activeMode = ref<WorkflowMode>('manual')
  const workflowName = ref('AIDD workflow')
  const workflowTemplateName = ref('AIDD workflow')
  const selectedSavedWorkflowId = ref<string | undefined>()
  const runningWorkflow = ref(false)
  const sidebarToolSearchKeyword = ref('')
  const workflowRunInputSelections = ref<Record<string, string | undefined>>({})
  const workflowRunAutoSyncTimer = ref<number | null>(null)

  const activeTemplate = computed(() => {
    return getWorkflowTemplateById(workflowStore.templateId) ?? AIDD_WORKFLOW_TEMPLATE
  })

  const editableTemplate = computed(() => ({
    ...activeTemplate.value,
    nodes: workflowStore.canvasNodes.length ? workflowStore.canvasNodes : activeTemplate.value.nodes,
    edges: workflowStore.canvasNodes.length ? workflowStore.canvasEdges : activeTemplate.value.edges
  }))

  const activeNode = computed(() => {
    const requestedNode = editableTemplate.value.nodes.find(node => node.id === workflowStore.activeNodeId)
    return requestedNode ?? editableTemplate.value.nodes[0] ?? null
  })

  const selectedToolByActiveNode = computed(() => {
    if (!activeNode.value) {
      return null
    }

    return resolveSelectedToolSlug(activeNode.value.id)
  })

  const templateOptions = computed(() => {
    return WORKFLOW_TEMPLATES.map(template => ({
      value: template.id,
      label: formatKey(template.nameKey)
    }))
  })

  const savedWorkflowOptions = computed(() => {
    return workflowDefinitionsStore.workflowDefinitions.map(workflow => ({
      value: workflow.id,
      label: workflow.name
    }))
  })

  const workflowTemplateOptions = computed(() => {
    return workflowStore.workflowTemplates.map(template => ({
      value: template.id,
      label: template.name
    }))
  })

  const currentWorkflowDefinition = computed<WorkflowDefinition>(() => buildCurrentWorkflowDefinition())

  const workflowInputRequirements = computed(() => {
    return extractWorkflowInputRequirements(currentWorkflowDefinition.value)
  })

  const selectedWorkflowInputFiles = computed(() => {
    return buildWorkflowInputFileMap(workflowInputRequirements.value, workflowRunInputSelections.value)
  })

  const availableWorkflowTools = computed(() => {
    const toolsBySlug = new Map<string, { id?: string; slug: string; name: string; description?: string }>()

    for (const group of toolsStore.workbenchGroups) {
      for (const tool of group.tools) {
        toolsBySlug.set(tool.slug, {
          id: tool.id,
          slug: tool.slug,
          name: tool.name,
          description: tool.description
        })
      }
    }

    for (const tool of toolsStore.workflowToolOptions) {
      if (!toolsBySlug.has(tool.slug)) {
        toolsBySlug.set(tool.slug, {
          id: tool.id,
          slug: tool.slug,
          name: tool.name,
          description: tool.description
        })
      }
    }

    return Array.from(toolsBySlug.values())
  })

  const filteredSidebarToolOptions = computed(() => {
    const keyword = sidebarToolSearchKeyword.value.trim().toLowerCase()
    if (!keyword) {
      return availableWorkflowTools.value
    }

    return availableWorkflowTools.value.filter(tool => {
      return [tool.name, tool.slug, tool.description]
        .filter(Boolean)
        .some(value => value!.toLowerCase().includes(keyword))
    })
  })

  const nodeStatuses = computed(() => {
    return editableTemplate.value.nodes.reduce<Record<string, ReturnType<typeof resolveWorkflowCanvasNodeStatus>>>(
      (statuses, node) => {
        statuses[node.id] = resolveWorkflowCanvasNodeStatus({
          node,
          selectedToolSlug: resolveSelectedToolSlug(node.id),
          hasRequiredInputs: hasRequiredInputs(node.id),
          task: workflowStore.taskByNode[node.id] ?? null
        })
        return statuses
      },
      {}
    )
  })

  const readyToolNodeIds = computed(() => {
    return resolveReadyToolNodeIds({
      template: editableTemplate.value,
      nodeStatuses: nodeStatuses.value
    })
  })

  const workflowPreflight = computed(() => {
    return buildWorkflowPreflight({
      template: editableTemplate.value,
      nodeStatuses: nodeStatuses.value,
      readyNodeIds: readyToolNodeIds.value
    })
  })

  const readyNodeCount = computed(() => readyToolNodeIds.value.length)
  const blockedNodeCount = computed(() => {
    return editableTemplate.value.nodes.filter(node => (
      node.type === 'tool' &&
      ['idle', 'needs_tool_selection'].includes(nodeStatuses.value[node.id] ?? 'idle')
    )).length
  })
  const runningNodeCount = computed(() => countNodesByStatus('running'))
  const completedNodeCount = computed(() => countNodesByStatus('completed'))
  const failedNodeCount = computed(() => countNodesByStatus('failed'))

  const workflowReportRows = computed<WorkflowReportRow[]>(() => {
    return editableTemplate.value.nodes.map(node => {
      const task = workflowStore.taskByNode[node.id]
      const artifacts = task
        ? artifactsStore.items
          .filter(artifact => artifact.task_id === task.id)
          .map(artifact => ({
            id: artifact.id,
            filename: artifact.filename,
            url: artifact.download_url
          }))
        : []

      return {
        nodeId: node.id,
        nodeTitle: formatKey(node.titleKey),
        status: nodeStatuses.value[node.id] ?? 'idle',
        statusLabel: resolveNodeStatusReason(node.id),
        taskId: task?.id,
        taskStatus: task?.status,
        artifacts
      }
    })
  })

  function handleTemplateChange(templateId: unknown) {
    if (typeof templateId !== 'string') {
      return
    }

    workflowStore.setTemplate(templateId)
  }

  function countNodesByStatus(status: ReturnType<typeof resolveWorkflowCanvasNodeStatus>) {
    return editableTemplate.value.nodes.filter(node => nodeStatuses.value[node.id] === status).length
  }

  function resolveNodeStatusReason(nodeId: string): string {
    const node = editableTemplate.value.nodes.find(item => item.id === nodeId)
    const status = nodeStatuses.value[nodeId] ?? 'idle'
    if (!node) {
      return ''
    }

    if (status === 'ready') {
      return '可运行'
    }
    if (status === 'running') {
      return '运行中'
    }
    if (status === 'completed') {
      return '已完成'
    }
    if (status === 'failed') {
      return '失败'
    }
    if (status === 'needs_tool_selection') {
      return '缺少工具'
    }
    if (status === 'invalidated') {
      return '需重跑'
    }
    if (node.type === 'tool' && node.requiredInputTypes?.length && !hasRequiredInputs(nodeId)) {
      return '等待上游'
    }

    return node.type === 'input' ? '输入节点' : '待准备'
  }

  function handleNodeToolSelect(nodeId: string, toolSlug: string) {
    workflowStore.selectNodeTool(nodeId, toolSlug)
  }

  function handleAddToolNode(toolSlug: string) {
    const tool = resolveAvailableTool(toolSlug)
    workflowStore.addToolNode({
      toolSlug,
      toolName: tool?.name ?? toolSlug,
      toolDescription: tool?.description,
      position: {
        x: 320 + editableTemplate.value.nodes.length * 36,
        y: 120 + editableTemplate.value.nodes.length * 24
      }
    })
  }

  function handleDeleteNode(nodeId: string) {
    workflowStore.deleteCanvasNode(nodeId)
  }

  function handleAddEdge(input: {
    source: string
    target: string
    artifactType: WorkflowArtifactSemanticType
  }) {
    workflowStore.addCanvasEdge(input)
  }

  function handleDeleteEdge(edgeId: string) {
    workflowStore.deleteCanvasEdge(edgeId)
  }

  async function handleNodeTaskSubmitted() {
    await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
  }

  async function handleRunNode(nodeId: string) {
    workflowStore.setActiveNode(nodeId)
    const node = editableTemplate.value.nodes.find(item => item.id === nodeId)
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
        priority: 'normal'
      })

      workflowStore.recordNodeTask(nodeId, toWorkflowTaskRef(task))
      message.success('节点任务已提交')
      if (isTaskTerminalStatus(task.status)) {
        await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
        return toWorkflowTaskRef(task)
      }

      return await pollNodeTaskUntilTerminal(nodeId, task.id)
    } catch {
      // 请求层会展示错误信息。
      return null
    }
  }

  async function prepareWorkflowNodeTaskPayload(nodeId: string, toolId: string) {
    const response = await getToolDetail(toolId)
    const tool = response.data
    const flattenedSchema = flattenToolInputSchema(resolveToolInputSchema(tool)) ?? {
      type: 'object',
      properties: {},
      required: []
    }
    const workflowParams = {
      workflow_template_id: editableTemplate.value.id,
      workflow_node_id: nodeId,
      workflow_node_type: editableTemplate.value.nodes.find(node => node.id === nodeId)?.type
    }
    const draft = {
      ...(workflowStore.nodeFormDrafts[nodeId] ?? {})
    }
    const uploadedFiles = resolveWorkflowNodeUploadedFiles(nodeId, flattenedSchema, draft)

    const payload = buildTaskSubmissionPayload({
      flattenedSchema,
      formState: draft,
      uploadedFiles,
      executorType: resolveToolExecutorType(tool)
    })

    return {
      params: {
        ...payload.params,
        ...workflowParams
      },
      fileIds: payload.fileIds
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
    draft: Record<string, unknown>
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
        downloadUrl: artifact.download_url
      }
    }

    return uploadedFiles
  }

  function resolveRecommendedArtifactsForNode(nodeId: string): ArtifactFile[] {
    return editableTemplate.value.edges
      .filter(edge => edge.target === nodeId)
      .map(edge => workflowStore.taskByNode[edge.source])
      .filter((task): task is WorkflowTaskRef => task?.status === 'success')
      .flatMap(task => artifactsStore.items.filter(artifact => artifact.task_id === task.id))
      .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
  }

  function findArtifactByUnknownId(value: unknown): ArtifactFile | null {
    if (typeof value !== 'string' && typeof value !== 'number') {
      return null
    }

    return artifactsStore.items.find(artifact => artifact.id === String(value)) ?? null
  }

  async function pollNodeTaskUntilTerminal(nodeId: string, taskId: string) {
    for (;;) {
      await new Promise(resolve => window.setTimeout(resolve, 3000))
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

  async function handleSaveWorkflow() {
    const name = workflowName.value.trim() || 'AIDD workflow'
    const payload: WorkflowDefinitionPayload = {
      name,
      template_id: editableTemplate.value.id,
      nodes: workflowStore.exportWorkflowNodes(editableTemplate.value.nodes),
      edges: workflowStore.exportWorkflowEdges(editableTemplate.value.edges),
      selected_tool_by_node: workflowStore.selectedToolByNode,
      artifact_bindings_by_node: workflowStore.artifactBindingsByNode,
      status: 'draft'
    }

    try {
      const saved = await workflowDefinitionsStore.saveWorkflowDefinition(
        payload,
        selectedSavedWorkflowId.value ?? workflowDefinitionsStore.currentWorkflowDefinition?.id
      )
      selectedSavedWorkflowId.value = saved.id
      workflowName.value = saved.name
      message.success('工作流已保存')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  function buildCurrentWorkflowDefinition(): WorkflowDefinition {
    const nodes = editableTemplate.value.nodes.map(node => ({
      id: node.id,
      kind: node.type === 'input' ? 'input' : 'tool',
      type: node.type,
      semantic_type: node.requiredInputTypes?.[0] ?? node.recommendedToolSlug ?? node.id,
      tool_slug: node.type === 'tool'
        ? resolveSelectedToolSlug(node.id) ?? node.recommendedToolSlug ?? undefined
        : undefined,
      semantic_inputs: buildSemanticInputsForNode(node.id),
      params: workflowStore.nodeFormDrafts[node.id] ?? {},
      position: node.position
    }))

    const edges = editableTemplate.value.edges.map(edge => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_output: edge.artifactType,
      target_input: edge.artifactType
    }))

    return { nodes, edges }
  }

  function buildSemanticInputsForNode(nodeId: string) {
    const semanticInputs: Record<string, string> = {}
    const node = editableTemplate.value.nodes.find(item => item.id === nodeId)
    if (!node) {
      return semanticInputs
    }

    const incomingEdges = editableTemplate.value.edges.filter(edge => edge.target === nodeId)
    for (const edge of incomingEdges) {
      if (!edge.artifactType) {
        continue
      }
      const sourceNode = editableTemplate.value.nodes.find(item => item.id === edge.source)
      if (!sourceNode) {
        continue
      }
      semanticInputs[edge.artifactType] = sourceNode.type === 'input'
        ? `workflow_input:${edge.artifactType}`
        : `node:${edge.source}:${edge.artifactType}`
    }

    for (const inputType of node.requiredInputTypes ?? []) {
      if (!semanticInputs[inputType]) {
        semanticInputs[inputType] = `workflow_input:${inputType}`
      }
    }

    return semanticInputs
  }

  async function handleNewWorkflowTemplate() {
    workflowStore.clearActiveWorkflowTemplate()
    workflowTemplateName.value = ''
    selectedSavedWorkflowId.value = undefined
  }

  async function handleTemplateSelect(templateId: string | undefined) {
    if (!templateId) {
      workflowStore.clearActiveWorkflowTemplate()
      return
    }

    try {
      const template = await workflowStore.loadWorkflowTemplate(templateId)
      workflowTemplateName.value = template.name
      selectedSavedWorkflowId.value = template.id
      workflowStore.applyWorkflowDefinition({
        template_id: template.id,
        name: template.name,
        description: template.description ?? undefined,
        nodes: (template.definition.nodes ?? []).map((node: any) => ({
          id: node.id,
          type: node.kind === 'input' ? 'input' : 'tool',
          titleKey: node.tool_slug || node.semantic_type || node.id,
          descriptionKey: node.tool_slug || node.semantic_type || node.id,
          position: node.position ?? { x: 0, y: 0 },
          toolSlugs: node.tool_slug ? [node.tool_slug] : [],
          recommendedToolSlug: node.tool_slug ?? undefined,
          requiredInputTypes: Object.keys(node.semantic_inputs ?? {}),
          producedOutputTypes: []
        })),
        edges: (template.definition.edges ?? []).map((edge: any, index: number) => ({
          id: edge.id ?? `edge-${index}`,
          source: edge.source,
          target: edge.target,
          artifactType: edge.source_output ?? edge.target_input
        })),
        selected_tool_by_node: {},
        artifact_bindings_by_node: {},
        status: 'draft'
      } as any)
    } catch {
      // 请求层会展示错误信息。
    }
  }

  async function handleSaveWorkflowTemplate() {
    const payload = {
      name: workflowTemplateName.value.trim() || 'AIDD workflow',
      description: workflowStore.activeWorkflowTemplate?.description ?? '',
      definition: buildCurrentWorkflowDefinition(),
      is_public: workflowStore.activeWorkflowTemplate?.is_public ?? false
    }

    try {
      const template = workflowStore.activeWorkflowTemplateId
        ? await workflowStore.updateSavedWorkflowTemplate(workflowStore.activeWorkflowTemplateId, payload)
        : await workflowStore.saveWorkflowTemplate(payload)
      workflowTemplateName.value = template.name
      selectedSavedWorkflowId.value = template.id
      message.success('工作流模板已保存')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  async function handleDuplicateWorkflowTemplate() {
    const templateId = workflowStore.activeWorkflowTemplateId
    if (!templateId) {
      return
    }

    try {
      const duplicated = await workflowStore.duplicateSavedWorkflowTemplate(
        templateId,
        `${workflowTemplateName.value || 'AIDD workflow'} Copy`
      )
      workflowTemplateName.value = duplicated.name
      selectedSavedWorkflowId.value = duplicated.id
      message.success('工作流模板已复制')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  async function handleDeleteWorkflowTemplate() {
    const templateId = workflowStore.activeWorkflowTemplateId
    if (!templateId) {
      return
    }

    try {
      await workflowStore.removeWorkflowTemplate(templateId)
      workflowTemplateName.value = 'AIDD workflow'
      selectedSavedWorkflowId.value = undefined
      message.success('工作流模板已删除')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  async function handleRunWorkflowTemplate() {
    const definition = buildCurrentWorkflowDefinition()
    const validationResult = validateWorkflowDefinition(definition)
    const executionValidationResult = validateWorkflowExecutionOrder(definition)
    if (!validationResult.valid || !executionValidationResult.valid) {
      message.warning(validationResult.message ?? executionValidationResult.message)
      return
    }

    const templateId = workflowStore.activeWorkflowTemplateId
    let activeTemplateId = templateId
    if (!activeTemplateId) {
      const template = await workflowStore.saveWorkflowTemplate({
        name: workflowTemplateName.value.trim() || 'AIDD workflow',
        definition: buildCurrentWorkflowDefinition(),
        is_public: false
      })
      activeTemplateId = template.id
      selectedSavedWorkflowId.value = template.id
    }

    const run = await workflowStore.runWorkflowTemplate(activeTemplateId!, {
      name: workflowTemplateName.value.trim() || 'AIDD workflow',
      input_files: selectedWorkflowInputFiles.value
    })
    await workflowStore.loadWorkflowRuns({ template_id: activeTemplateId!, page: 1, page_size: 20 })
    await workflowStore.loadWorkflowRun(run.id)
  }

  async function handleRefreshWorkflowRuns() {
    const templateId = workflowStore.activeWorkflowTemplateId ?? undefined
    await workflowStore.loadWorkflowRuns({ template_id: templateId, page: 1, page_size: 20 })
  }

  async function handleLoadMoreWorkflowRuns() {
    const templateId = workflowStore.activeWorkflowTemplateId ?? undefined
    if (!workflowStore.hasMoreWorkflowRuns) {
      return
    }
    await workflowStore.loadWorkflowRuns(
      {
        template_id: templateId,
        page: workflowStore.workflowRunsPagination.page + 1,
        page_size: workflowStore.workflowRunsPagination.pageSize
      },
      { append: true }
    )
  }

  async function handleWorkflowRunSelect(runId: string) {
    await workflowStore.loadWorkflowRun(runId)
    await scheduleWorkflowRunAutoSync()
  }

  async function handleSyncWorkflowRun() {
    await workflowStore.syncActiveWorkflowRun()
  }

  async function autofillWorkflowInputSelections() {
    const nextSelections: Record<string, string | undefined> = {}
    for (const semanticType of workflowInputRequirements.value) {
      const artifact = findLatestArtifactForSemanticType(artifactsStore.items, semanticType)
      nextSelections[semanticType] = artifact?.id
    }
    workflowRunInputSelections.value = nextSelections
  }

  function getArtifactOptionsForSemanticType(semanticType: string) {
    return artifactsStore.items
      .filter(artifact => artifact.semantic_type === semanticType)
      .map(artifact => ({
        value: artifact.id,
        label: `${artifact.filename} · ${artifact.tool_name}`
      }))
  }

  function handleWorkflowInputSelect(semanticType: string, artifactId: string | undefined) {
    workflowRunInputSelections.value = {
      ...workflowRunInputSelections.value,
      [semanticType]: artifactId
    }
  }

  async function scheduleWorkflowRunAutoSync() {
    clearWorkflowRunAutoSync()
    const run = workflowStore.activeWorkflowRun
    if (!shouldAutoSyncWorkflowRun(run, {
      isLoggedIn: userStore.isLoggedIn,
      isLoading: workflowStore.isLoadingWorkflowRun,
      isSyncing: workflowStore.isSyncingWorkflowRun
    })) {
      return
    }

    workflowRunAutoSyncTimer.value = window.setInterval(async () => {
      await workflowStore.syncActiveWorkflowRun()
    }, 5000)
  }

  function clearWorkflowRunAutoSync() {
    if (workflowRunAutoSyncTimer.value !== null) {
      window.clearInterval(workflowRunAutoSyncTimer.value)
      workflowRunAutoSyncTimer.value = null
    }
  }

  async function restoreActiveWorkflowTemplate() {
    if (!workflowStore.activeWorkflowTemplateId) {
      return
    }
    await handleTemplateSelect(workflowStore.activeWorkflowTemplateId)
  }

  async function restoreActiveWorkflowRun() {
    if (!workflowStore.activeWorkflowRunId) {
      return
    }
    await workflowStore.loadWorkflowRun(workflowStore.activeWorkflowRunId)
  }

  async function handleLoadWorkflow() {
    if (!selectedSavedWorkflowId.value) {
      return
    }

    try {
      const workflow = await workflowDefinitionsStore.loadWorkflowDefinition(selectedSavedWorkflowId.value)
      workflowStore.applyWorkflowDefinition(workflow)
      workflowName.value = workflow.name
      message.success('工作流已加载')
    } catch {
      // 请求层会展示错误信息。
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
        const orderedNodeIds = resolveWorkflowExecutionOrder({
          template: editableTemplate.value,
          candidateNodeIds: readyToolNodeIds.value
        }).filter(nodeId => {
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

  function hasRequiredInputs(nodeId: string): boolean {
    const node = editableTemplate.value.nodes.find(item => item.id === nodeId)
    if (!node?.requiredInputTypes?.length) {
      return true
    }

    return node.requiredInputTypes.every(inputType => {
      return editableTemplate.value.edges.some(edge => {
        const upstreamTask = workflowStore.taskByNode[edge.source]
        return edge.target === nodeId && edge.artifactType === inputType && upstreamTask?.status === 'success'
      })
    })
  }

  function resolveSelectedToolSlug(nodeId: string): string | null {
    const node = editableTemplate.value.nodes.find(item => item.id === nodeId)
    if (!node) {
      return null
    }

    return workflowStore.selectedToolByNode[nodeId] ?? node.recommendedToolSlug ?? node.toolSlugs?.[0] ?? null
  }

  function resolveToolForNode(nodeId: string) {
    const selectedToolSlug = resolveSelectedToolSlug(nodeId)
    if (!selectedToolSlug) {
      return null
    }

    const workbenchTool = toolsStore.workbenchGroups
      .flatMap(group => group.tools)
      .find(tool => tool.slug === selectedToolSlug) ?? null
    if (workbenchTool) {
      return workbenchTool
    }

    return toolsStore.workflowToolOptions.find(tool => tool.slug === selectedToolSlug) ?? null
  }

  function resolveAvailableTool(toolSlug: string) {
    return availableWorkflowTools.value.find(tool => tool.slug === toolSlug) ?? null
  }

  function formatKey(key: string): string {
    const segments = key.split('.')
    const lastSegment = segments[segments.length - 1] ?? key
    return lastSegment
      .replace(/([A-Z])/g, ' $1')
      .replace(/[-_]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  }

  watch(
    activeTemplate,
    (template) => {
      workflowStore.ensureCanvasFromTemplate(template)
      if (!editableTemplate.value.nodes.some(node => node.id === workflowStore.activeNodeId)) {
        workflowStore.setActiveNode(editableTemplate.value.nodes[0]?.id ?? null)
      }
    },
    { immediate: true }
  )

  watch(
    () => [userStore.isLoggedIn, userStore.user?.id] as const,
    async ([isLoggedIn, userId]) => {
      workflowStore.syncOwnerUserId(isLoggedIn ? userId ?? undefined : undefined)

      if (!isLoggedIn) {
        artifactsStore.resetArtifacts()
        workflowDefinitionsStore.clearCurrentWorkflowDefinition()
        selectedSavedWorkflowId.value = undefined
        clearWorkflowRunAutoSync()
        return
      }

      await Promise.allSettled([
        artifactsStore.fetchArtifacts({ page: 1, page_size: 100 }),
        workflowDefinitionsStore.fetchWorkflowDefinitions({ page: 1, page_size: 100 }),
        workflowStore.loadWorkflowTemplates(),
        workflowStore.loadWorkflowRuns({ page: 1, page_size: 20 })
      ])
    },
    { immediate: true }
  )

  watch(
    () => workflowStore.activeWorkflowRunId,
    async () => {
      await scheduleWorkflowRunAutoSync()
    }
  )

  onMounted(async () => {
    await Promise.allSettled([
      toolsStore.fetchWorkbenchGroups(),
      toolsStore.fetchWorkflowTools()
    ])
  })

  onMounted(async () => {
    await restoreActiveWorkflowTemplate()
    await restoreActiveWorkflowRun()
  })

  function buildWorkflowReportRows() {
    return workflowReportRows.value
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-page {
    padding: @spacing-xl 0 @spacing-xxl;
    min-height: calc(100vh - @header-height - @footer-height);
    background:
      radial-gradient(circle at top, rgba(13, 110, 253, 0.08) 0%, rgba(255, 255, 255, 0) 32%),
      linear-gradient(180deg, rgba(24, 144, 255, 0.06) 0%, rgba(255, 255, 255, 0) 260px),
      @bg-light;
  }

  .workflow-shell {
    width: min(100%, calc(100vw - 32px));
    max-width: none;
    margin: 0 auto;
  }

  .workflow-deck {
    position: relative;
    padding: @spacing-sm;
    border-radius: 32px;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.45) 0%, rgba(255, 255, 255, 0.18) 100%),
      linear-gradient(135deg, rgba(13, 110, 253, 0.04) 0%, rgba(46, 196, 182, 0.04) 100%);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
  }

  .workflow-mode-tabs {
    :deep(.ant-tabs-nav) {
      margin: 0 0 @spacing-lg;
      padding: 0 @spacing-md;
    }

    :deep(.ant-tabs-tab) {
      padding: @spacing-sm @spacing-md;
      color: @text-color-light-secondary;
      font-weight: 600;
      letter-spacing: 0;
    }

    :deep(.ant-tabs-tab-active .ant-tabs-tab-btn) {
      color: @primary-color;
      font-weight: 700;
    }
  }

  .workflow-definition-bar {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    padding: @spacing-md;
    margin-bottom: @spacing-md;
    border: 1px solid rgba(24, 144, 255, 0.12);
    border-radius: @border-radius-md;
    background: rgba(255, 255, 255, 0.86);
    box-shadow: @shadow-sm;
  }

  .workflow-name-input {
    width: min(280px, 100%);
  }

  .workflow-load-select {
    width: min(320px, 100%);
  }

  .workflow-preflight-region {
    margin-bottom: @spacing-md;
  }

  .workflow-template-layout {
    display: grid;
    grid-template-columns: minmax(220px, 260px) minmax(0, 1fr) minmax(300px, 360px);
    gap: @spacing-md;
    align-items: start;
  }

  .workflow-results-region {
    margin-top: @spacing-md;
  }

  .template-step-rail {
    min-width: 0;
    max-height: 720px;
    display: flex;
    flex-direction: column;
    border: 1px solid rgba(24, 144, 255, 0.12);
    border-radius: @border-radius-md;
    background: @bg-light-secondary;
    box-shadow: @shadow-sm;
    overflow: hidden;
  }

  .template-selector {
    padding: @spacing-md;
    border-bottom: 1px solid @border-color-light;
  }

  .rail-kicker {
    display: block;
    margin-bottom: @spacing-xs;
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .template-select {
    width: 100%;
  }

  .template-node-list {
    display: grid;
    gap: @spacing-xs;
    padding: @spacing-sm;
    max-height: 260px;
    overflow: auto;
  }

  .template-node-item {
    width: 100%;
    display: grid;
    gap: @spacing-xs;
    padding: @spacing-sm;
    border: 1px solid transparent;
    border-radius: @border-radius-sm;
    background: transparent;
    color: @text-color-light-primary;
    text-align: left;
    cursor: pointer;
  }

  .template-node-item:hover,
  .template-node-item.is-active {
    border-color: rgba(24, 144, 255, 0.22);
    background: @primary-color-light;
  }

  .node-item-title {
    min-width: 0;
    font-size: @font-size-sm;
    font-weight: 700;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .node-item-reason {
    min-width: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .workflow-status-summary {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: @spacing-xs;
    padding: @spacing-sm;
    border-bottom: 1px solid @border-color-light;
  }

  .status-summary-item {
    min-width: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-xs;
    padding: @spacing-xs @spacing-sm;
    border: 1px solid rgba(24, 144, 255, 0.1);
    border-radius: @border-radius-sm;
    background: rgba(255, 255, 255, 0.78);
  }

  .status-summary-item span {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .status-summary-item strong {
    color: @text-color-light-primary;
    font-size: @font-size-md;
  }

  .status-summary-item.is-ready strong {
    color: @success-color;
  }

  .status-summary-item.is-blocked strong {
    color: @warning-color;
  }

  .status-summary-item.is-running strong {
    color: @primary-color;
  }

  .status-summary-item.is-failed strong {
    color: @error-color;
  }

  .workflow-sidebar-tool-library {
    min-height: 0;
    display: flex;
    flex-direction: column;
    border-top: 1px solid @border-color-light;
  }

  .sidebar-tool-library-header {
    display: grid;
    gap: @spacing-xs;
    padding: @spacing-sm;
  }

  .sidebar-tool-list {
    display: grid;
    gap: @spacing-xs;
    padding: 0 @spacing-sm @spacing-sm;
    overflow: auto;
  }

  .sidebar-tool-item {
    min-width: 0;
    display: grid;
    gap: 3px;
    padding: @spacing-sm;
    border: 1px solid rgba(24, 144, 255, 0.12);
    border-radius: @border-radius-sm;
    background: rgba(255, 255, 255, 0.82);
    text-align: left;
    cursor: pointer;
  }

  .sidebar-tool-item:hover,
  .sidebar-tool-item:focus-visible {
    border-color: rgba(24, 144, 255, 0.42);
    background: @primary-color-light;
    outline: none;
  }

  .sidebar-tool-name {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    font-weight: 800;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sidebar-tool-desc {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .sidebar-tool-action {
    color: @primary-color;
    font-size: @font-size-xs;
    font-weight: 700;
  }

  .sidebar-tool-empty {
    padding: @spacing-sm 0;
  }

  @media (max-width: @screen-xl) {
    .workflow-template-layout {
      grid-template-columns: 220px minmax(0, 1fr);
    }

    .workflow-node-inspector {
      grid-column: 1 / -1;
    }
  }

  @media (max-width: @screen-md) {
    .workflow-definition-bar {
      align-items: stretch;
      flex-direction: column;
    }

    .workflow-name-input,
    .workflow-load-select {
      width: 100%;
    }

    .workflow-template-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
