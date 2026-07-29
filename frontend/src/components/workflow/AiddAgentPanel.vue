<template>
  <section class="aidd-agent-panel">
    <div class="agent-control-panel">
      <div class="agent-panel-head">
        <div>
          <span class="agent-kicker">{{ t('workflow.agent.kicker') }}</span>
          <h2>{{ t('workflow.agent.title') }}</h2>
          <p>{{ t('workflow.agent.subtitle') }}</p>
        </div>
        <a-tag color="blue">{{ t('workflow.agent.autoRouting') }}</a-tag>
      </div>

      <div class="capability-strip">
        <span
          v-for="item in capabilityOptions"
          :key="item.key"
          class="capability-chip"
        >
          <span class="capability-dot" />
          <span class="capability-copy">
            <strong>{{ item.title }}</strong>
            <small>{{ item.description }}</small>
          </span>
        </span>
      </div>

      <a-form class="agent-form" layout="vertical">
        <a-form-item :label="t('workflow.agent.messageLabel')">
          <a-textarea
            v-model:value="runMessage"
            :placeholder="t('workflow.agent.messagePlaceholder')"
            :auto-size="{ minRows: 4, maxRows: 6 }"
            :maxlength="500"
            show-count
          />
        </a-form-item>

        <div class="agent-submit-row">
          <a-form-item class="agent-file-field" :label="t('workflow.agent.inputFiles')">
            <a-upload
              v-model:file-list="agentFileUploads"
              accept=".pdb,.ent,.cif,.sdf,.csv"
              :before-upload="beforeUpload"
              :multiple="true"
            >
              <a-button>
                <UploadOutlined />
                {{ t('workflow.agent.selectInputFiles') }}
              </a-button>
            </a-upload>
            <p class="agent-file-hint">{{ t('workflow.agent.fileAutoDetectHint') }}</p>
          </a-form-item>

          <div class="agent-actions">
            <a-button
              size="large"
              :loading="draftSubmitting || agentsStore.drafting"
              :disabled="submitting"
              @click="generateWorkflowDraft"
            >
              <ApartmentOutlined />
              {{ t('workflow.agent.generateDraft') }}
            </a-button>
            <a-button
              type="primary"
              size="large"
              :loading="submitting || agentsStore.loading"
              :disabled="draftSubmitting || agentsStore.drafting"
              @click="createRun"
            >
              <PlayCircleOutlined />
              {{ t('workflow.agent.run') }}
            </a-button>
            <a-button
              v-if="agentsStore.currentRun"
              size="large"
              :loading="syncing"
              @click="syncRun"
            >
              <SyncOutlined />
              {{ t('workflow.agent.sync') }}
            </a-button>
            <a-button
              v-if="agentsStore.currentRun && !['success', 'failure', 'canceled'].includes(agentsStore.currentRun.status)"
              danger
              size="large"
              @click="cancelRun"
            >
              {{ t('common.cancel') }}
            </a-button>
          </div>
        </div>
      </a-form>
    </div>

    <div class="agent-runtime-panel">
      <div class="runtime-header">
        <div>
          <span class="agent-kicker">{{ t('workflow.agent.timeline') }}</span>
          <h3>{{ currentRunTitle }}</h3>
        </div>
        <a-tag v-if="agentsStore.currentRun" :color="runStatusColor(agentsStore.currentRun.status)">
          {{ t(`workflow.agent.status.${agentsStore.currentRun.status}`) }}
        </a-tag>
      </div>

      <div v-if="agentsStore.currentRun" class="run-meta">
        <span>{{ t('workflow.agent.autoRouting') }}</span>
        <span>{{ agentsStore.currentRun.steps.length }} steps</span>
        <span>{{ agentsStore.currentRun.intent }}</span>
      </div>

      <div v-if="analysisTrace.length > 0" class="agent-analysis-panel">
        <span class="agent-kicker">{{ t('workflow.agent.analysis') }}</span>
        <ol class="agent-analysis-list">
          <li v-for="(item, index) in analysisTrace" :key="index">
            {{ item }}
          </li>
        </ol>
      </div>

      <div class="agent-history-panel">
        <div class="history-head">
          <span class="agent-kicker">{{ t('workflow.agent.history') }}</span>
          <a-button type="link" size="small" :loading="agentsStore.loading" @click="loadRecentRuns">
            <ReloadOutlined />
            {{ t('common.refresh') }}
          </a-button>
        </div>
        <a-checkbox v-model:checked="cascadeDeleteHistory" class="cascade-delete-checkbox">
          {{ t('workflow.agent.cascadeDeleteHistory') }}
        </a-checkbox>
        <a-empty
          v-if="historyRuns.length === 0"
          class="history-empty"
          :description="t('workflow.agent.noHistory')"
        />
        <div v-else class="history-list">
          <div
            v-for="run in historyRuns"
            :key="run.id"
            class="history-item"
            :class="{ 'is-active': run.id === agentsStore.currentRun?.id }"
          >
            <button
              type="button"
              class="history-select-button"
              @click="selectHistoryRun(run.id)"
            >
              <span class="history-message">{{ run.message }}</span>
              <span class="history-meta">
                <a-tag :color="runStatusColor(run.status)">
                  {{ t(`workflow.agent.status.${run.status}`) }}
                </a-tag>
                <span>{{ formatRunTime(run.created_at) }}</span>
              </span>
            </button>
            <a-popconfirm
              :title="cascadeDeleteHistory ? t('workflow.agent.cascadeDeleteHistoryConfirm') : t('workflow.agent.deleteHistoryConfirm')"
              @confirm="deleteHistoryRun(run.id)"
            >
              <a-button
                type="text"
                size="small"
                danger
                :loading="deletingRunId === run.id"
                :aria-label="t('workflow.agent.deleteHistory')"
                @click.stop
              >
                <DeleteOutlined />
              </a-button>
            </a-popconfirm>
          </div>
        </div>
      </div>

      <a-empty
        v-if="!agentsStore.currentRun"
        class="agent-empty"
        :description="t('workflow.agent.empty')"
      />
      <a-timeline v-else class="agent-timeline">
        <a-timeline-item
          v-for="step in orderedSteps"
          :key="step.id"
          :color="stepStatusColor(step.status)"
        >
          <div class="step-card">
            <div class="step-main">
              <span class="step-index">#{{ String(step.sort_order + 1).padStart(2, '0') }}</span>
              <strong>{{ formatStepTitle(step.step_key) }}</strong>
              <span class="step-meta">{{ formatToolSlug(step.tool_slug) }}</span>
              <p v-if="step.error_message" class="step-error">{{ step.error_message }}</p>
            </div>
            <div class="step-actions">
              <a-tag :color="stepStatusColor(step.status)">
                {{ t(`workflow.agent.stepStatus.${step.status}`) }}
              </a-tag>
              <a-button
                v-if="step.task_id"
                type="link"
                size="small"
                @click="viewTask(step.task_id)"
              >
                {{ t('workflow.agent.viewTask') }}
              </a-button>
            </div>
          </div>
        </a-timeline-item>
      </a-timeline>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { UploadFile } from 'ant-design-vue'
  import {
    ApartmentOutlined,
    DeleteOutlined,
    PlayCircleOutlined,
    ReloadOutlined,
    SyncOutlined,
    UploadOutlined
  } from '@ant-design/icons-vue'
  import { uploadFile } from '@/api/files'
  import { useAgentsStore, useUserStore } from '@/stores'
  import type {
    AiddAgentRun,
    AiddAgentRunCreateParams,
    AiddAgentRunStatus,
    AiddAgentStepStatus,
    AiddWorkflowDraft
  } from '@/types/models'

  const emit = defineEmits<{
    draftGenerated: [draft: AiddWorkflowDraft]
  }>()

  const router = useRouter()
  const { t } = useI18n()
  const agentsStore = useAgentsStore()
  const userStore = useUserStore()

  const runMessage = ref('')
  const agentFileUploads = ref<UploadFile[]>([])
  const submitting = ref(false)
  const draftSubmitting = ref(false)
  const syncing = ref(false)
  const deletingRunId = ref<string | null>(null)
  const cascadeDeleteHistory = ref(false)

  const capabilityOptions = computed(() => {
    return [
      {
        key: 'pocket_exploration',
        title: t('workflow.steps.pocketExploration.title'),
        description: t('workflow.steps.pocketExploration.description')
      },
      {
        key: 'molecule_generation',
        title: t('workflow.steps.moleculeGenerationOrVirtualScreening.title'),
        description: t('workflow.steps.moleculeGenerationOrVirtualScreening.description')
      },
      {
        key: 'binding_evaluation',
        title: t('workflow.steps.molecularDockingAndAffinityPrediction.title'),
        description: t('workflow.steps.molecularDockingAndAffinityPrediction.description')
      },
      {
        key: 'property_prediction',
        title: t('workflow.steps.propertyPrediction.title'),
        description: t('workflow.steps.propertyPrediction.description')
      }
    ]
  })

  const orderedSteps = computed(() => {
    return [...(agentsStore.currentRun?.steps ?? [])].sort((left, right) => left.sort_order - right.sort_order)
  })

  const historyRuns = computed<AiddAgentRun[]>(() => {
    return agentsStore.runs
  })

  const currentRunTitle = computed(() => {
    return agentsStore.currentRun?.summary || agentsStore.currentRun?.message || t('workflow.agent.noRun')
  })

  const analysisTrace = computed(() => {
    const trace = agentsStore.currentRun?.plan?.analysis_trace
    if (Array.isArray(trace)) {
      return trace
        .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
        .map(item => item.trim())
    }

    const summary = agentsStore.currentRun?.plan?.reasoning_summary
    return typeof summary === 'string' && summary.trim() ? [summary.trim()] : []
  })

  function beforeUpload() {
    return false
  }

  async function loadRecentRuns() {
    if (!userStore.isLoggedIn) {
      return
    }

    await agentsStore.fetchRuns({ page: 1, page_size: 5 })
  }

  function formatStepTitle(stepKey: string) {
    const labels: Record<string, string> = {
      pocket_prediction: t('workflow.steps.pocketExploration.title'),
      molecule_generation: t('workflow.steps.moleculeGenerationOrVirtualScreening.title'),
      property_prediction: t('workflow.steps.propertyPrediction.title'),
      affinity_prediction: t('workflow.steps.molecularDockingAndAffinityPrediction.title')
    }

    return labels[stepKey] ?? stepKey
  }

  function formatToolSlug(toolSlug: string) {
    return toolSlug.replace(/-/g, ' ').toUpperCase()
  }

  function runStatusColor(status: AiddAgentRunStatus) {
    const colors: Record<AiddAgentRunStatus, string> = {
      pending: 'default',
      planning: 'processing',
      running: 'processing',
      waiting_task: 'processing',
      success: 'success',
      failure: 'error',
      canceled: 'warning'
    }

    return colors[status]
  }

  function stepStatusColor(status: AiddAgentStepStatus) {
    const colors: Record<AiddAgentStepStatus, string> = {
      pending: 'gray',
      ready: 'blue',
      running: 'blue',
      waiting_task: 'blue',
      success: 'green',
      failure: 'red',
      skipped: 'gray',
      canceled: 'orange'
    }

    return colors[status]
  }

  function formatRunTime(value?: string | null) {
    if (!value) {
      return '-'
    }
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
      return value
    }
    return date.toLocaleString()
  }

  async function selectHistoryRun(runId: string) {
    await agentsStore.fetchRun(runId)
  }

  async function deleteHistoryRun(runId: string) {
    deletingRunId.value = runId
    try {
      const result = await agentsStore.deleteRun(runId, cascadeDeleteHistory.value)
      if (cascadeDeleteHistory.value) {
        message.success(
          t('workflow.agent.cascadeDeleted', {
            tasks: result.deleted_tasks,
            artifacts: result.deleted_artifacts
          })
        )
      } else {
        message.success(t('workflow.agent.deleted'))
      }
    } finally {
      deletingRunId.value = null
    }
  }

  async function prepareAgentRequest(): Promise<AiddAgentRunCreateParams | null> {
    if (!userStore.isLoggedIn) {
      message.warning(t('workflow.agent.loginRequired'))
      router.push('/login')
      return null
    }

    const selectedFiles = agentFileUploads.value.filter(item => Boolean(item.originFileObj))
    if (selectedFiles.length === 0) {
      message.warning(t('workflow.agent.uploadRequired'))
      return null
    }

    const uploadedFileIds: string[] = []
    for (const uploadItem of selectedFiles) {
      const uploaded = await uploadFile(uploadItem.originFileObj as File)
      uploadedFileIds.push(uploaded.data.id.toString())
    }
    return {
      message: runMessage.value.trim() || t('workflow.agent.defaultMessage'),
      input_file_ids: uploadedFileIds
    }
  }

  async function createRun() {
    submitting.value = true
    try {
      const request = await prepareAgentRequest()
      if (!request) {
        return
      }
      const run = await agentsStore.createRun(request)

      agentsStore.pollRunUntilTerminal(run.id)
      message.success(t('workflow.agent.created'))
    } finally {
      submitting.value = false
    }
  }

  async function generateWorkflowDraft() {
    draftSubmitting.value = true
    try {
      const request = await prepareAgentRequest()
      if (!request) {
        return
      }
      const draft = await agentsStore.createWorkflowDraft(request)
      emit('draftGenerated', draft)
      message.success(t('workflow.agent.draftGenerated'))
    } finally {
      draftSubmitting.value = false
    }
  }

  async function syncRun() {
    if (!agentsStore.currentRun) {
      return
    }

    syncing.value = true
    try {
      await agentsStore.syncRun(agentsStore.currentRun.id)
    } finally {
      syncing.value = false
    }
  }

  async function cancelRun() {
    if (!agentsStore.currentRun) {
      return
    }

    await agentsStore.cancelRun(agentsStore.currentRun.id)
    agentsStore.clearPolling()
  }

  function viewTask(taskId: string) {
    router.push('/tasks/' + taskId)
  }

  watch(
    () => [userStore.isLoggedIn, userStore.user?.id] as const,
    () => {
      void loadRecentRuns()
    }
  )

  onMounted(() => {
    void loadRecentRuns()
  })

  onBeforeUnmount(() => {
    agentsStore.clearPolling()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .aidd-agent-panel {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(360px, 0.8fr);
    gap: @spacing-lg;
    margin-bottom: 0;

    @media (max-width: @screen-lg) {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  .agent-control-panel,
  .agent-runtime-panel {
    min-width: 0;
    border: 1px solid @border-color-hover;
    border-radius: 18px;
    background: @bg-surface;
    box-shadow: 0 18px 36px rgb(15 23 42 / 5%);
  }

  .agent-control-panel {
    padding: @spacing-lg;
  }

  .agent-runtime-panel {
    padding: @spacing-lg;
  }

  .agent-panel-head,
  .runtime-header,
  .step-card,
  .step-actions {
    display: flex;
    align-items: flex-start;
  }

  .agent-panel-head,
  .runtime-header {
    justify-content: space-between;
    gap: @spacing-md;
    margin-bottom: @spacing-md;
  }

  .agent-panel-head h2,
  .runtime-header h3 {
    margin: 4px 0;
    color: @text-color-light-primary;
    font-weight: 700;
    letter-spacing: 0;
  }

  .agent-panel-head p {
    margin: 0;
    color: @text-color-light-secondary;
    line-height: 1.7;
  }

  .agent-kicker {
    color: @primary-color;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0;
  }

  .capability-strip {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: @spacing-sm;
    margin-bottom: @spacing-lg;

    @media (max-width: @screen-md) {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  .capability-chip {
    display: flex;
    align-items: flex-start;
    gap: @spacing-sm;
    min-width: 0;
    padding: @spacing-sm;
    border: 1px solid @accent-color-border;
    border-radius: @border-radius-md;
    background: @accent-color-light;
    color: @text-color-light-primary;
    font-size: @font-size-sm;
  }

  .capability-dot {
    flex: none;
    width: 8px;
    height: 8px;
    margin-top: 7px;
    border-radius: @border-radius-round;
    background: @primary-color;
  }

  .capability-copy {
    min-width: 0;

    strong,
    small {
      display: block;
      overflow-wrap: anywhere;
    }

    strong {
      color: @text-color-light-primary;
      font-weight: @font-weight-semibold;
    }

    small {
      margin-top: 2px;
      color: @text-color-light-secondary;
      line-height: @line-height-base;
    }
  }

  .step-index {
    color: @primary-color;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    font-weight: @font-weight-semibold;
  }

  .agent-form {
    min-width: 0;
  }

  .agent-submit-row {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: flex-end;
    flex-wrap: wrap;
  }

  .agent-file-field {
    min-width: 260px;
    margin-bottom: 0;
    flex: 1;
  }

  .agent-file-hint {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
  }

  .agent-actions {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-sm;
  }

  .run-meta {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-xs;
    margin-bottom: @spacing-lg;

    span {
      padding: 4px 8px;
      border-radius: @border-radius-sm;
      background: @bg-hover;
      color: @text-secondary;
      font-size: @font-size-xs;
    }
  }

  .agent-analysis-panel {
    margin: -@spacing-xs 0 @spacing-lg;
    padding: @spacing-sm @spacing-md;
    border-left: 3px solid @primary-color;
    border-radius: @border-radius-sm;
    background: linear-gradient(90deg, rgba(59, 130, 246, 0.07), rgba(59, 130, 246, 0.02));
  }

  .agent-analysis-list {
    display: grid;
    gap: 6px;
    margin: 6px 0 0;
    padding-left: 18px;
    color: @text-color-light-primary;
    line-height: @line-height-base;

    li {
      overflow-wrap: anywhere;
    }
  }

  .agent-empty {
    padding: @spacing-xl 0;
  }

  .agent-timeline {
    margin-top: @spacing-md;
  }

  .agent-history-panel {
    margin-bottom: @spacing-lg;
    padding: @spacing-sm;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-elevated;
  }

  .history-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
    margin-bottom: @spacing-sm;
  }

  .history-empty {
    padding: @spacing-md 0;
  }

  .cascade-delete-checkbox {
    margin-bottom: @spacing-sm;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .history-list {
    display: grid;
    gap: @spacing-xs;
    max-height: 260px;
    overflow: auto;
  }

  .history-item {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    width: 100%;
    border: 1px solid transparent;
    border-radius: @border-radius-sm;
    background: @bg-hover;
    color: @text-color-light-primary;
    transition: border-color @transition-fast, background @transition-fast;

    &:hover,
    &.is-active {
      border-color: rgba(59, 130, 246, 0.25);
      background: rgba(59, 130, 246, 0.05);
    }
  }

  .history-select-button {
    display: grid;
    gap: @spacing-xs;
    min-width: 0;
    flex: 1;
    padding: @spacing-sm;
    border: 0;
    background: transparent;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }

  .history-message {
    display: -webkit-box;
    overflow: hidden;
    color: @text-color-light-primary;
    font-weight: @font-weight-semibold;
    line-height: @line-height-base;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .history-meta {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    flex-wrap: wrap;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .step-card {
    justify-content: space-between;
    gap: @spacing-md;
    padding: @spacing-sm @spacing-md;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-elevated;
  }

  .step-main {
    min-width: 0;

    strong,
    span {
      display: block;
    }
  }

  .step-meta {
    color: @text-color-light-secondary;
    font-size: 12px;
  }

  .step-actions {
    flex-shrink: 0;
    gap: @spacing-xs;
  }

  .step-error {
    margin: 4px 0 0;
    color: @error-color;
    font-size: 12px;
  }

  @media (max-width: @screen-sm) {
    .agent-submit-row,
    .agent-actions,
    .agent-actions :deep(.ant-btn) {
      width: 100%;
    }

    .semantic-file-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
