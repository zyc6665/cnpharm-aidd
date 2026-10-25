<template>
  <main class="result-detail-page">
    <router-link
      v-if="projectId"
      :to="`/projects/${projectId}/results`"
      class="back-link"
      data-testid="result-back"
    >
      {{ t('results.detail.backToResults') }}
    </router-link>

    <AppPageHeader :title="resultTitle" :subtitle="t('results.detail.summary')">
      <template #actions>
        <a-button :loading="loading" data-testid="result-refresh" @click="loadAll">
          {{ t('common.refresh') }}
        </a-button>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="loadError"
      class="result-alert"
      type="error"
      show-icon
      data-testid="result-error"
      :message="t('results.errors.loadResult')"
    >
      <template #action>
        <a-button size="small" @click="loadAll">{{ t('common.refresh') }}</a-button>
      </template>
    </a-alert>

    <SkeletonDetail v-if="loading && !result" />

    <template v-else-if="result">
      <section class="result-section">
        <h3 class="section-title">{{ t('results.detail.summary') }}</h3>
        <a-descriptions bordered :column="2" size="small" data-testid="result-summary">
          <a-descriptions-item :label="t('results.columns.name')">
            {{ result.name || result.task_id }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('results.columns.status')">
            <a-tag :color="result.status === 'success' ? 'green' : 'red'">
              {{ t(`tasks.status.${result.status}`) }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item :label="t('results.detail.submittedBy')">
            {{ result.submitted_by || '-' }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('results.columns.executionTime')">
            {{ formatExecutionSeconds(result.execution_time_sec) }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('results.detail.startTime')">
            {{ formatDate(result.started_at) }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('results.detail.finishTime')">
            {{ formatDate(result.finished_at) }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('results.detail.project')" :span="2">
            <router-link :to="`/projects/${result.project_id}`">
              {{ result.project_id }}
            </router-link>
          </a-descriptions-item>
        </a-descriptions>

        <a-alert
          v-if="result.error_message"
          class="result-alert"
          type="error"
          show-icon
          data-testid="result-error-message"
          :message="t('results.detail.errorMessage')"
          :description="result.error_message"
        />
      </section>

      <section class="result-section">
        <h3 class="section-title">{{ t('results.detail.outputs') }}</h3>
        <a-table
          v-if="result.outputs.length > 0"
          :columns="outputColumns"
          :data-source="result.outputs"
          :pagination="false"
          row-key="id"
          size="small"
          data-testid="result-output-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              {{ record.name || record.filename || record.id }}
            </template>
            <template v-else-if="column.key === 'sha256'">
              <span class="mono-cell">{{ shortHash(record.sha256) }}</span>
            </template>
            <template v-else-if="column.key === 'size_bytes'">
              {{ formatBytes(record.size_bytes) }}
            </template>
          </template>
        </a-table>
        <p v-else class="section-empty" data-testid="result-output-empty">
          {{ t('results.detail.noOutputs') }}
        </p>
      </section>

      <section class="result-section">
        <h3 class="section-title">{{ t('results.detail.inputs') }}</h3>
        <a-table
          v-if="result.inputs.length > 0"
          :columns="inputColumns"
          :data-source="inputRows"
          :pagination="false"
          :row-key="(record: ResultInputSnapshot) => `${record.ordinal}-${record.entityId ?? ''}`"
          size="small"
          data-testid="result-input-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'urn'">
              <span class="mono-cell">{{ record.urn || '-' }}</span>
            </template>
            <template v-else-if="column.key === 'sha256'">
              <span class="mono-cell">{{ shortHash(record.sha256) }}</span>
            </template>
            <template v-else-if="column.key === 'recordedAt'">
              {{ formatDate(record.recordedAt) }}
            </template>
          </template>
        </a-table>
        <p v-else class="section-empty" data-testid="result-input-empty">
          {{ t('results.detail.noInputs') }}
        </p>
      </section>

      <!-- 追溯包：复用 getTraceability，不新建追溯组件 -->
      <section class="result-section">
        <div class="traceability-header">
          <div>
            <h3 class="section-title">{{ t('results.traceability.title') }}</h3>
            <p class="section-subtitle">{{ t('results.traceability.subtitle') }}</p>
          </div>
          <a-space>
            <span v-if="traceability" class="traceability-version" data-testid="traceability-version">
              {{ t('results.traceability.packageVersion') }}: {{ traceability.packageVersion }}
            </span>
            <a-button
              type="primary"
              :loading="exporting"
              data-testid="traceability-export"
              @click="handleExport"
            >
              {{ exporting ? t('results.traceability.exporting') : t('results.traceability.export') }}
            </a-button>
          </a-space>
        </div>

        <a-alert
          v-if="traceabilityError"
          class="result-alert"
          type="error"
          show-icon
          data-testid="traceability-error"
          :message="t('results.errors.loadTraceability')"
        >
          <template #action>
            <a-button size="small" @click="loadTraceability">{{ t('common.refresh') }}</a-button>
          </template>
        </a-alert>

        <a-spin :spinning="traceabilityLoading">
          <a-collapse v-if="traceability" v-model:activeKey="activeSections" data-testid="traceability-panel">
            <a-collapse-panel
              v-for="section in TRACEABILITY_SECTIONS"
              :key="section.key"
              :header="t(section.labelKey)"
            >
              <div :data-testid="`traceability-section-${section.key}`">
                <!-- 任务信息 -->
                <a-descriptions
                  v-if="section.key === 'task'"
                  bordered
                  :column="2"
                  size="small"
                >
                  <a-descriptions-item :label="t('results.traceability.fields.taskId')">
                    {{ traceability.taskId }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.taskName')">
                    {{ traceability.taskName || '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.taskType')">
                    {{ traceability.taskType || '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.status')">
                    {{ traceability.status || '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.submittedBy')">
                    {{ traceability.submittedBy?.displayName || traceability.submittedBy?.userId || '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.packageVersion')">
                    {{ traceability.packageVersion }}
                  </a-descriptions-item>
                </a-descriptions>

                <!-- 时间线 -->
                <a-descriptions
                  v-else-if="section.key === 'timeline'"
                  bordered
                  :column="2"
                  size="small"
                >
                  <a-descriptions-item :label="t('results.traceability.fields.created')">
                    {{ formatDate(traceability.timeline?.created) }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.started')">
                    {{ formatDate(traceability.timeline?.started) }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.finished')">
                    {{ formatDate(traceability.timeline?.finished) }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.executionSeconds')">
                    {{ formatExecutionSeconds(traceability.timeline?.executionSeconds) }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.retryCount')">
                    {{ traceability.timeline?.retryCount ?? 0 }}
                  </a-descriptions-item>
                </a-descriptions>

                <!-- 输入快照 -->
                <a-table
                  v-else-if="section.key === 'inputs'"
                  :columns="traceInputColumns"
                  :data-source="traceInputRows"
                  :pagination="false"
                  :row-key="(record: TraceabilityInput) => `${record.ordinal ?? 0}-${record.entityId ?? ''}`"
                  size="small"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'urn'">
                      <span class="mono-cell">{{ record.urn || '-' }}</span>
                    </template>
                    <template v-else-if="column.key === 'sha256'">
                      <span class="mono-cell">{{ shortHash(record.sha256) }}</span>
                    </template>
                  </template>
                </a-table>

                <!-- 运行环境 -->
                <a-descriptions
                  v-else-if="section.key === 'environment'"
                  bordered
                  :column="2"
                  size="small"
                >
                  <a-descriptions-item :label="t('results.traceability.fields.image')">
                    <span class="mono-cell">{{ traceability.environment?.image || '-' }}</span>
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.executorType')">
                    {{ traceability.environment?.executorType || '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.tool')">
                    {{ traceability.environment?.tool?.name || '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.model')">
                    {{ traceability.environment?.model || '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.contractVersion')">
                    {{ traceability.environment?.contractVersion || '-' }}
                  </a-descriptions-item>
                </a-descriptions>

                <!-- 执行过程 -->
                <a-descriptions
                  v-else-if="section.key === 'process'"
                  bordered
                  :column="2"
                  size="small"
                >
                  <a-descriptions-item :label="t('results.traceability.fields.exitMessage')">
                    {{ traceability.process?.exitMessage || '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item :label="t('results.traceability.fields.logAvailable')">
                    {{ traceability.process?.logAvailable ? '✓' : '✗' }}
                  </a-descriptions-item>
                </a-descriptions>

                <!-- 产物清单 -->
                <a-table
                  v-else
                  :columns="traceOutputColumns"
                  :data-source="traceability.outputs"
                  :pagination="false"
                  :row-key="(record: TraceabilityOutput) => `${record.urn ?? ''}-${record.filename ?? ''}`"
                  size="small"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'urn'">
                      <span class="mono-cell">{{ record.urn || '-' }}</span>
                    </template>
                    <template v-else-if="column.key === 'sha256'">
                      <span class="mono-cell">{{ shortHash(record.sha256) }}</span>
                    </template>
                    <template v-else-if="column.key === 'sizeBytes'">
                      {{ formatBytes(record.sizeBytes) }}
                    </template>
                  </template>
                </a-table>
              </div>
            </a-collapse-panel>
          </a-collapse>

          <p v-else-if="!traceabilityError" class="section-empty" data-testid="traceability-empty">
            {{ t('results.traceability.empty') }}
          </p>
        </a-spin>
      </section>
    </template>

    <p v-else class="section-empty" data-testid="result-not-found">
      {{ t('results.errors.loadResult') }}
    </p>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import dayjs from 'dayjs'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import { exportTraceability, getResult, getTraceability } from '@/api/results'
  import { TRACEABILITY_SECTIONS, formatExecutionSeconds } from '@/domain/results'
  import { triggerProtectedFileDownload } from '@/utils/protected-file-access'
  import type {
    ProjectResultDetail,
    ResultInputSnapshot,
    TraceabilityInput,
    TraceabilityOutput,
    TraceabilityPackage
  } from '@/types/compounds'

  const route = useRoute()
  const { t } = useI18n()

  const taskId = computed(() => String(route.params.taskId || ''))

  const loading = ref(false)
  const loadError = ref(false)
  const result = ref<ProjectResultDetail | null>(null)

  const traceabilityLoading = ref(false)
  const traceabilityError = ref(false)
  const traceability = ref<TraceabilityPackage | null>(null)
  const activeSections = ref<string[]>(['task'])

  const exporting = ref(false)

  const resultTitle = computed(() => result.value?.name || t('results.detail.title'))

  const projectId = computed(() => {
    const fromResult = result.value?.project_id
    if (fromResult) return fromResult
    return String(route.query.project_id || '')
  })

  const inputRows = computed<ResultInputSnapshot[]>(() => result.value?.inputs ?? [])

  const traceInputRows = computed<TraceabilityInput[]>(() => traceability.value?.inputs ?? [])

  const outputColumns = computed(() => [
    { title: t('results.detail.outputs'), dataIndex: 'name', key: 'name', width: 220 },
    { title: t('results.traceability.fields.artifactType'), dataIndex: 'artifact_type', key: 'artifact_type', width: 140 },
    { title: t('results.traceability.fields.semanticType'), dataIndex: 'semantic_type', key: 'semantic_type', width: 140 },
    { title: t('results.traceability.fields.filename'), dataIndex: 'filename', key: 'filename', width: 180 },
    { title: t('results.traceability.fields.sha256'), key: 'sha256', width: 160 },
    { title: t('common.status'), key: 'size_bytes', width: 100 }
  ])

  const inputColumns = computed(() => [
    { title: t('candidates.set.columns.ordinal'), dataIndex: 'ordinal', key: 'ordinal', width: 80 },
    { title: t('results.traceability.fields.inputRole'), dataIndex: 'inputRole', key: 'inputRole', width: 120 },
    { title: t('results.traceability.fields.entityType'), dataIndex: 'entityType', key: 'entityType', width: 120 },
    { title: t('results.traceability.fields.entityId'), dataIndex: 'entityId', key: 'entityId', width: 160 },
    { title: t('results.traceability.fields.urn'), key: 'urn', width: 200 },
    { title: t('results.traceability.fields.sha256'), key: 'sha256', width: 140 },
    { title: t('results.detail.finishTime'), key: 'recordedAt', width: 160 }
  ])

  const traceInputColumns = computed(() => [
    { title: t('candidates.set.columns.ordinal'), dataIndex: 'ordinal', key: 'ordinal', width: 80 },
    { title: t('results.traceability.fields.inputRole'), dataIndex: 'inputRole', key: 'inputRole', width: 120 },
    { title: t('results.traceability.fields.entityId'), dataIndex: 'entityId', key: 'entityId', width: 160 },
    { title: t('results.traceability.fields.urn'), key: 'urn', width: 240 },
    { title: t('results.traceability.fields.sha256'), key: 'sha256', width: 140 }
  ])

  const traceOutputColumns = computed(() => [
    { title: t('results.traceability.fields.artifactType'), dataIndex: 'artifactType', key: 'artifactType', width: 140 },
    { title: t('results.traceability.fields.semanticType'), dataIndex: 'semanticType', key: 'semanticType', width: 140 },
    { title: t('results.traceability.fields.filename'), dataIndex: 'filename', key: 'filename', width: 180 },
    { title: t('results.traceability.fields.urn'), key: 'urn', width: 220 },
    { title: t('results.traceability.fields.sha256'), key: 'sha256', width: 140 },
    { title: t('common.status'), key: 'sizeBytes', width: 100 }
  ])

  function formatDate(value: string | null | undefined): string {
    return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
  }

  function shortHash(value: string | null | undefined): string {
    if (!value) return '-'
    return value.length > 12 ? `${value.slice(0, 12)}…` : value
  }

  function formatBytes(value: number | null | undefined): string {
    if (value === null || value === undefined) return '-'
    if (value < 1024) return `${value} B`
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
    return `${(value / (1024 * 1024)).toFixed(1)} MB`
  }

  async function loadResult(): Promise<void> {
    if (!taskId.value) return

    loadError.value = false
    try {
      const response = await getResult(taskId.value)
      result.value = response.data
    } catch {
      loadError.value = true
      result.value = null
    }
  }

  async function loadTraceability(): Promise<void> {
    if (!taskId.value) return

    traceabilityLoading.value = true
    traceabilityError.value = false
    try {
      const response = await getTraceability(taskId.value)
      traceability.value = response.data
    } catch {
      traceabilityError.value = true
      traceability.value = null
    } finally {
      traceabilityLoading.value = false
    }
  }

  async function loadAll(): Promise<void> {
    if (!taskId.value) return

    loading.value = true
    await Promise.allSettled([loadResult(), loadTraceability()])
    loading.value = false
  }

  async function handleExport(): Promise<void> {
    if (!taskId.value) return

    exporting.value = true
    try {
      const response = await exportTraceability(taskId.value)
      const payload = response.data
      if (payload.download_url) {
        await triggerProtectedFileDownload({
          url: payload.download_url,
          filename: payload.filename ?? undefined
        })
      }
      message.success(t('results.traceability.exported'))
      await loadTraceability()
    } catch {
      message.error(t('results.errors.exportTraceability'))
    } finally {
      exporting.value = false
    }
  }

  onMounted(() => {
    void loadAll()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .result-detail-page {
    max-width: 1240px;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;
  }

  .result-alert {
    margin-top: @spacing-md;
    margin-bottom: @spacing-md;
  }

  .result-section {
    margin-bottom: @spacing-xl;
  }

  .section-title {
    margin: 0 0 @spacing-sm;
    color: @text-primary;
    font-size: @font-size-lg;
  }

  .section-subtitle {
    margin: 0 0 @spacing-md;
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .section-empty {
    padding: @spacing-lg;
    color: @text-tertiary;
    text-align: center;
    background: @bg-surface;
    border: 1px dashed @border-color;
    border-radius: @border-radius-md;
  }

  .traceability-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-md;
  }

  .traceability-version {
    color: @text-tertiary;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
  }

  .mono-cell {
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    word-break: break-all;
  }
</style>
