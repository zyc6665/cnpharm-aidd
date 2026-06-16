<template>
  <div class="workflow-page">
    <div class="workflow-shell workflow-deck">
      <AppPageHeader :title="t('workflow.title')" :subtitle="t('workflow.subtitle')" align="center" />

      <a-tabs v-model:activeKey="activeMode" class="workflow-mode-tabs">
        <a-tab-pane key="manual" :tab="t('workflow.mode.manual')">
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

              <div class="template-node-list">
                <button
                  v-for="node in activeTemplate.nodes"
                  :key="node.id"
                  type="button"
                  class="template-node-item"
                  :class="{ 'is-active': node.id === activeNode?.id }"
                  @click="workflowStore.setActiveNode(node.id)"
                >
                  <span class="node-item-title">{{ formatKey(node.titleKey) }}</span>
                  <WorkflowNodeStatusBadge :status="nodeStatuses[node.id] ?? 'idle'" />
                </button>
              </div>
            </aside>

            <WorkflowTemplateCanvas
              :template="activeTemplate"
              :active-node-id="activeNode?.id ?? null"
              :node-statuses="nodeStatuses"
              @select-node="workflowStore.setActiveNode"
            />

            <WorkflowNodeInspector
              :node="activeNode"
              :template="activeTemplate"
              :artifacts="artifactsStore.items"
              :task-by-node="workflowStore.taskByNode"
              :status="activeNode ? nodeStatuses[activeNode.id] : 'idle'"
              :selected-tool-slug="activeNode ? selectedToolByActiveNode : null"
              :task="activeNode ? workflowStore.taskByNode[activeNode.id] ?? null : null"
              @select-tool="handleNodeToolSelect"
              @run-node="handleRunNode"
            />
          </div>
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
  import WorkflowNodeStatusBadge from '@/components/workflow/WorkflowNodeStatusBadge.vue'
  import WorkflowTemplateCanvas from '@/components/workflow/WorkflowTemplateCanvas.vue'
  import { useArtifactsStore, useTasksStore, useToolsStore, useUserStore, useWorkflowStore } from '@/stores'
  import { resolveWorkflowCanvasNodeStatus } from '@/workflow/template-state'
  import {
    AIDD_WORKFLOW_TEMPLATE,
    WORKFLOW_TEMPLATES,
    getWorkflowTemplateById
  } from '@/workflow/templates'

  const { t } = useI18n()
  const artifactsStore = useArtifactsStore()
  const tasksStore = useTasksStore()
  const toolsStore = useToolsStore()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()

  type WorkflowMode = 'manual' | 'agent'

  const activeMode = ref<WorkflowMode>('manual')

  const activeTemplate = computed(() => {
    return getWorkflowTemplateById(workflowStore.templateId) ?? AIDD_WORKFLOW_TEMPLATE
  })

  const activeNode = computed(() => {
    const requestedNode = activeTemplate.value.nodes.find(node => node.id === workflowStore.activeNodeId)
    return requestedNode ?? activeTemplate.value.nodes[0] ?? null
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

  const nodeStatuses = computed(() => {
    return activeTemplate.value.nodes.reduce<Record<string, ReturnType<typeof resolveWorkflowCanvasNodeStatus>>>(
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

  function handleTemplateChange(templateId: unknown) {
    if (typeof templateId !== 'string') {
      return
    }

    workflowStore.setTemplate(templateId)
  }

  function handleNodeToolSelect(nodeId: string, toolSlug: string) {
    workflowStore.selectNodeTool(nodeId, toolSlug)
  }

  async function handleRunNode(nodeId: string) {
    workflowStore.setActiveNode(nodeId)
    const node = activeTemplate.value.nodes.find(item => item.id === nodeId)
    if (!node) {
      return
    }

    const tool = resolveToolForNode(nodeId)
    if (!tool) {
      message.warning('当前节点缺少可运行工具')
      return
    }

    try {
      const task = await tasksStore.createTask({
        name: formatKey(node.titleKey),
        tool_id: tool.id,
        params: {
          workflow_template_id: activeTemplate.value.id,
          workflow_node_id: node.id,
          workflow_node_type: node.type
        },
        priority: 'normal'
      })

      workflowStore.recordNodeTask(nodeId, task)
      message.success('节点任务已提交')
      await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
    } catch {
      // 请求层会展示错误信息。
    }
  }

  function hasRequiredInputs(nodeId: string): boolean {
    const node = activeTemplate.value.nodes.find(item => item.id === nodeId)
    if (!node?.requiredInputTypes?.length) {
      return true
    }

    return node.requiredInputTypes.every(inputType => {
      return activeTemplate.value.edges.some(edge => {
        const upstreamTask = workflowStore.taskByNode[edge.source]
        return edge.target === nodeId && edge.artifactType === inputType && upstreamTask?.status === 'success'
      })
    })
  }

  function resolveSelectedToolSlug(nodeId: string): string | null {
    const node = activeTemplate.value.nodes.find(item => item.id === nodeId)
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

    return toolsStore.workbenchGroups
      .flatMap(group => group.tools)
      .find(tool => tool.slug === selectedToolSlug) ?? null
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
      if (!template.nodes.some(node => node.id === workflowStore.activeNodeId)) {
        workflowStore.setActiveNode(template.nodes[0]?.id ?? null)
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
        return
      }

      await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
    },
    { immediate: true }
  )

  onMounted(async () => {
    await toolsStore.fetchWorkbenchGroups()
  })
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

  .workflow-template-layout {
    display: grid;
    grid-template-columns: minmax(220px, 260px) minmax(0, 1fr) minmax(300px, 360px);
    gap: @spacing-md;
    align-items: start;
  }

  .template-step-rail {
    min-width: 0;
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

  @media (max-width: @screen-xl) {
    .workflow-template-layout {
      grid-template-columns: 220px minmax(0, 1fr);
    }

    .workflow-node-inspector {
      grid-column: 1 / -1;
    }
  }

  @media (max-width: @screen-md) {
    .workflow-template-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
