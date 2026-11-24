<template>
  <div class="md-result" data-testid="md-result-page">
    <app-page-header :title="t('md.result.title')" :subtitle="t('md.result.subtitle')">
      <template #actions>
        <a-button v-if="taskId" @click="reload" :loading="loading">{{ t('md.common.refresh') }}</a-button>
      </template>
    </app-page-header>

    <TaskContextBar
      v-if="taskId"
      :task-id="taskId"
      active="result"
      :task="task"
      :result-path="route.fullPath"
      :fetch-task="false"
    />

    <skeleton-detail v-if="loading && !result" />

    <a-result v-else-if="loadError" status="warning" :title="t('md.common.loadFailed')" :sub-title="loadError">
      <template #extra>
        <a-button type="primary" @click="reload">{{ t('md.common.retry') }}</a-button>
      </template>
    </a-result>

    <template v-else>
      <a-card :bordered="false" class="md-result__overview">
        <AppDescriptionList :sections="overviewSections" :columns="2" test-id="md-overview" />
        <div v-if="isRunning" class="md-result__progress" data-testid="md-progress">
          <a-progress :percent="progressPercent" :status="'active'" />
          <p class="md-result__progress-text">
            {{ t('md.result.progressLabel', { percent: progressPercent }) }}
            <template v-if="totalFrames"> · {{ t('md.result.frameProgress', { current: currentFrame, total: totalFrames }) }}</template>
            <template v-if="progressMessage"> · {{ progressMessage }}</template>
          </p>
        </div>
      </a-card>

      <a-alert v-if="analysisLoadErrors.length" type="warning" show-icon class="md-result__notice" :message="t('md.result.analysisLoadFailed', { roles: analysisLoadErrors.join(', ') })" />
      <p v-if="analysisRows.length > 600 || rmsfRows.length > 600" class="md-result__sample-hint">{{ t('md.result.sampledDisplay') }}</p>
      <a-alert
        v-if="!topologyFile && !analysisFile && !isRunning"
        type="info" show-icon class="md-result__notice" :message="t('md.result.noTrajectoryArtifact')"
      />
      <a-row :gutter="16" class="md-result__grid">
        <a-col :xs="24" :lg="12"><a-card :bordered="false" :title="t('md.result.charts.rmsd')" size="small">
          <md-echart v-if="rmsdOption" :option="rmsdOption" /><a-empty v-else :description="t('md.result.chartEmpty')" />
        </a-card></a-col>
        <a-col :xs="24" :lg="12"><a-card :bordered="false" :title="t('md.result.charts.rmsf')" size="small">
          <md-echart v-if="rmsfOption" :option="rmsfOption" /><a-empty v-else :description="t('md.result.chartEmpty')" />
        </a-card></a-col>
        <a-col :xs="24" :lg="12"><a-card :bordered="false" :title="t('md.result.charts.rg')" size="small">
          <md-echart v-if="rgOption" :option="rgOption" /><a-empty v-else :description="t('md.result.chartEmpty')" />
        </a-card></a-col>
        <a-col :xs="24" :lg="12"><a-card :bordered="false" :title="t('md.result.charts.temperature')" size="small">
          <md-echart v-if="temperatureOption" :option="temperatureOption" /><a-empty v-else :description="t('md.result.chartEmpty')" />
        </a-card></a-col>
      </a-row>
      <a-row :gutter="16" class="md-result__grid">
        <a-col :xs="24" :lg="12"><a-card :bordered="false" :title="t('md.result.outputs')" size="small">
          <a-space direction="vertical" fill>
            <a-button block :disabled="!trajectoryFile" data-testid="md-download-trajectory" @click="downloadRole('trajectory_dcd')">{{ t('md.result.downloadTrajectory') }}</a-button>
            <a-button block :disabled="!analysisFile" data-testid="md-download-analysis" @click="downloadRole('analysis_csv')">{{ t('md.result.downloadAnalysis') }}</a-button>
            <a-button block :disabled="!topologyFile" data-testid="md-download-topology" @click="downloadRole('topology_pdb')">{{ t('md.result.downloadTopology') }}</a-button>
            <a-button block :disabled="!metadataFile" @click="downloadRole('metadata_json')">{{ t('md.result.downloadMetadata') }}</a-button>
          </a-space>
          <a-alert type="warning" show-icon class="md-result__notice" :message="t('md.result.trajectoryNotice')" />
        </a-card></a-col>
        <a-col :xs="24" :lg="12"><a-card :bordered="false" :title="t('md.result.structurePreview')" size="small">
          <div class="md-result__viewer">
            <structure-artifact-preview v-if="artifact && topologyFile" :artifact="artifact" :preferred-file-roles="['topology_pdb']" />
            <a-empty v-else :description="t('md.result.noTopology')" />
          </div>
          <p class="md-result__viewer-note">{{ t('md.result.staticPreviewNote') }}</p>
        </a-card></a-col>
      </a-row>
    </template>
  </div>
  <ResultDisclaimer />
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { EChartsOption } from 'echarts'
  import Papa from 'papaparse'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import AppDescriptionList from '@/components/common/AppDescriptionList.vue'
  import StructureArtifactPreview from '@/components/artifacts/StructureArtifactPreview.vue'
  import MdEchart from './MdEchart.vue'
  import { getArtifactDetail, getMdResult } from '@/api/md'
  import { getTaskDetail } from '@/api/tasks'
  import { openTaskEventStream } from '@/api/task-events'
  import { fetchProtectedFileText, triggerProtectedFileDownload } from '@/utils/protected-file-access'
  import { buildAnalysisRows, buildRmsfRows, downsampleSeries, findOutputByStandardType } from './analysis'
  import type { DescriptionSection } from '@/components/common/AppDescriptionList.vue'
  import type { ArtifactVersionFile, TypedArtifact } from '@/types/artifacts'
  import type { MdAnalysisRow, MdResultDetail, MdTrajectoryMetadata, MdTrajectoryRole, RmsfRow } from '@/types/md'
  import type { Task } from '@/types/models'
  import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'

  interface PapaParseResult { data: Array<Record<string, string>> }
  const { t } = useI18n()
  const route = useRoute()
  const taskId = computed(() => String(route.params.id ?? ''))
  const result = ref<MdResultDetail | null>(null)
  const task = ref<Task | null>(null)
  const artifact = ref<TypedArtifact | null>(null)
  const analysisRows = ref<MdAnalysisRow[]>([])
  const rmsfRows = ref<RmsfRow[]>([])
  const metadata = ref<MdTrajectoryMetadata>({})
  const analysisLoadErrors = ref<string[]>([])
  const loading = ref(false)
  const loadError = ref('')
  const progressPercent = ref(0)
  const progressMessage = ref('')
  let streamHandle: { close: () => void } | null = null
  let disposed = false
  let requestSequence = 0
  let artifactIdLoaded: string | null = null
  const files = computed<ArtifactVersionFile[]>(() => artifact.value?.latest_version.files ?? [])
  function roleFile(role: MdTrajectoryRole): ArtifactVersionFile | null { return files.value.find(file => file.role === role) ?? null }
  const analysisFile = computed(() => roleFile('analysis_csv'))
  const rmsfFile = computed(() => roleFile('rmsf_csv'))
  const metadataFile = computed(() => roleFile('metadata_json'))
  const topologyFile = computed(() => roleFile('topology_pdb'))
  const trajectoryFile = computed(() => roleFile('trajectory_dcd'))
  const status = computed(() => result.value?.status ?? task.value?.status ?? '')
  const isRunning = computed(() => ['running', 'pending', 'queued'].includes(status.value))
  const statusColor = computed(() => ({ success: 'green', running: 'blue', pending: 'blue', queued: 'blue', failure: 'red', canceled: 'orange' } as Record<string, string>)[status.value] ?? 'default')
  const totalFrames = computed(() => {
    const value = Number(metadata.value.total_frames)
    if (Number.isFinite(value) && value > 0) return Math.round(value)
    return analysisRows.value.length || null
  })
  const currentFrame = computed(() => !totalFrames.value ? 0 : Math.min(totalFrames.value, Math.round(totalFrames.value * progressPercent.value / 100)))
  function parseCsv(text: string): Array<Record<string, string>> {
    return (Papa as unknown as { parse: (input: string, config: Record<string, unknown>) => PapaParseResult })
      .parse(text, { header: true, skipEmptyLines: true }).data
  }
  function lineOption(x: number[], y: number[], yName: string): EChartsOption {
    return { grid: { left: 48, right: 16, top: 24, bottom: 36 }, tooltip: { trigger: 'axis' }, xAxis: { type: 'value', name: t('md.result.chartXAxis'), nameLocation: 'middle', nameGap: 24 }, yAxis: { type: 'value', name: yName }, series: [{ type: 'line', smooth: true, showSymbol: false, data: x.map((value, index) => [value, y[index]]) }] }
  }
  function buildChartOption(field: keyof MdAnalysisRow, yName: string): EChartsOption | null {
    const data = analysisRows.value.filter(row => typeof row[field] === 'number')
    if (!data.length) return null
    const sampled = downsampleSeries(data, 600, row => row[field] as number | null)
    return lineOption(sampled.map(row => row.time_ps), sampled.map(row => Number(row[field])), yName)
  }
  const rmsdOption = computed(() => buildChartOption('rmsd_nm', 'RMSD (nm)'))
  const rmsfOption = computed<EChartsOption | null>(() => {
    if (rmsfRows.value.length) {
      const sampled = downsampleSeries(rmsfRows.value, 600, row => row.rmsf_nm)
      return { grid: { left: 48, right: 16, top: 24, bottom: 40 }, tooltip: { trigger: 'axis' }, xAxis: { type: 'value', name: t('md.result.chartResidueAxis'), nameLocation: 'middle', nameGap: 24 }, yAxis: { type: 'value', name: 'RMSF (nm)' }, series: [{ type: 'line', smooth: true, showSymbol: false, data: sampled.map(row => [row.residue_seq, row.rmsf_nm]) }] }
    }
    return buildChartOption('rmsf_nm', 'RMSF (nm)')
  })
  const rgOption = computed(() => buildChartOption('rg_nm', 'Rg (nm)'))
  const temperatureOption = computed(() => buildChartOption('temperature_k', 'T (K)'))

  async function loadAnalysisAndMetadata(sequence: number): Promise<void> {
    analysisRows.value = []; rmsfRows.value = []; metadata.value = {}; analysisLoadErrors.value = []
    const errors: string[] = []
    if (analysisFile.value) {
      try { const text = await fetchProtectedFileText(analysisFile.value.download_url); if (!disposed && sequence === requestSequence) analysisRows.value = buildAnalysisRows(parseCsv(text)) }
      catch { errors.push('analysis_csv') }
    }
    if (rmsfFile.value) {
      try { const text = await fetchProtectedFileText(rmsfFile.value.download_url); if (!disposed && sequence === requestSequence) rmsfRows.value = buildRmsfRows(parseCsv(text)) }
      catch { errors.push('rmsf_csv') }
    }
    if (metadataFile.value) {
      try { const text = await fetchProtectedFileText(metadataFile.value.download_url); const parsed = JSON.parse(text) as MdTrajectoryMetadata; if (!disposed && sequence === requestSequence) metadata.value = parsed }
      catch { errors.push('metadata_json') }
    }
    if (!disposed && sequence === requestSequence) analysisLoadErrors.value = errors
  }
  function stopStream(): void { streamHandle?.close(); streamHandle = null }
  function startStream(sequence: number, id: string): void {
    if (streamHandle) return
    const handle = openTaskEventStream(id, {
      onProgress: payload => { if (disposed || sequence !== requestSequence) return; progressPercent.value = Math.max(0, Math.min(100, Math.round(payload.progress))); progressMessage.value = payload.progressMessage ?? '' },
      onStatus: payload => { if (disposed || sequence !== requestSequence) return; progressPercent.value = Math.max(0, Math.min(100, Math.round(payload.progress))); progressMessage.value = payload.progressMessage ?? ''; if (payload.status && result.value) result.value.status = payload.status; if (payload.terminal) { stopStream(); void reload() } },
      onDone: () => { if (disposed || sequence !== requestSequence) return; stopStream(); void reload() }
    })
    streamHandle = handle.available ? handle : null
  }
  async function reload(): Promise<void> {
    const id = taskId.value
    if (!id || disposed) return
    const sequence = ++requestSequence
    stopStream(); loading.value = true; loadError.value = ''
    try {
      const [detail, taskDetail] = await Promise.all([getMdResult(id), getTaskDetail(id).catch(() => null)])
      if (disposed || sequence !== requestSequence) return
      result.value = detail; task.value = taskDetail?.data ?? null; progressPercent.value = Math.round(taskDetail?.data.progress ?? 0)
      const output = findOutputByStandardType(detail.outputs, 'md_trajectory@1')
      const nextArtifact = output ? await getArtifactDetail(output.id) : null
      if (disposed || sequence !== requestSequence) return
      const nextId = nextArtifact?.id ?? null
      if (artifactIdLoaded !== nextId) { analysisRows.value = []; rmsfRows.value = []; metadata.value = {}; analysisLoadErrors.value = []; artifactIdLoaded = nextId }
      artifact.value = nextArtifact
      if (nextArtifact) await loadAnalysisAndMetadata(sequence)
      if (disposed || sequence !== requestSequence) return
      if (isRunning.value) startStream(sequence, id); else stopStream()
    } catch (error) {
      if (!disposed && sequence === requestSequence) loadError.value = error instanceof Error ? error.message : String(error)
    } finally { if (!disposed && sequence === requestSequence) loading.value = false }
  }
  async function downloadRole(role: MdTrajectoryRole): Promise<void> {
    const file = roleFile(role); if (!file) return
    try { await triggerProtectedFileDownload({ url: file.download_url, filename: file.filename ?? undefined }) }
    catch (cause) { message.error(cause instanceof Error ? cause.message : String(cause)) }
  }
  watch(taskId, () => { result.value = null; task.value = null; artifact.value = null; artifactIdLoaded = null; analysisRows.value = []; rmsfRows.value = []; metadata.value = {}; analysisLoadErrors.value = []; void reload() }, { immediate: true })
  onMounted(() => { disposed = false })
  onBeforeUnmount(() => { disposed = true; requestSequence += 1; stopStream() })
  const overviewSections = computed<DescriptionSection[]>(() => [{ key: 'overview', fields: [
    { key: 'status', label: t('md.result.taskStatus'), value: result.value?.status ?? '-', tagColor: statusColor.value },
    { key: 'forceField', label: t('md.result.forceField'), value: metadata.value.force_field ?? '-' },
    { key: 'totalFrames', label: t('md.result.totalFrames'), value: totalFrames.value != null ? String(totalFrames.value) : '-' },
    { key: 'duration', label: t('md.result.duration'), value: metadata.value.duration_ns != null ? `${metadata.value.duration_ns} ns` : '-', hint: t('md.result.hints.duration') },
    { key: 'temperature', label: t('md.result.temperature'), value: metadata.value.temperature_k != null ? `${metadata.value.temperature_k} K` : '-', hint: t('md.result.hints.temperature') },
    { key: 'timestep', label: t('md.result.timestep'), value: metadata.value.timestep_ps != null ? `${metadata.value.timestep_ps} ps` : '-', hint: t('md.result.hints.timestep') }
  ] }])
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';
  .md-result { max-width: @page-max-width; margin: 0 auto; }
  .md-result__overview { margin-bottom: @spacing-md; border-radius: @border-radius-lg; }
  .md-result__progress { margin-top: @spacing-md; }
  .md-result__progress-text { margin: @spacing-xs 0 0; color: @text-color-light-secondary; font-size: @font-size-sm; }
  .md-result__grid { margin-bottom: @spacing-sm; }
  .md-result__notice { margin-top: @spacing-md; }
  .md-result__viewer { height: 360px; border: 1px solid @border-color; border-radius: @border-radius-md; overflow: hidden; }
  .md-result__viewer-note { margin: @spacing-xs 0 0; color: @text-color-light-secondary; font-size: @font-size-xs; }
</style>
