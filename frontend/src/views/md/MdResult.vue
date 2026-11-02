<template>
  <div class="md-result" data-testid="md-result-page">
    <app-page-header :title="t('md.result.title')" :subtitle="t('md.result.subtitle')">
      <template #actions>
        <a-button v-if="taskId" @click="reload" :loading="loading">{{ t('md.common.refresh') }}</a-button>
      </template>
    </app-page-header>


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

      <a-alert
        v-if="!topologyFile && !analysisFile && !isRunning"
        type="info"
        show-icon
        class="md-result__notice"
        :message="t('md.result.noTrajectoryArtifact')"
      />

      <a-row :gutter="16" class="md-result__grid">
        <a-col :xs="24" :lg="12">
          <a-card :bordered="false" :title="t('md.result.charts.rmsd')" size="small">
            <md-echart v-if="rmsdOption" :option="rmsdOption" />
            <a-empty v-else :description="t('md.result.chartEmpty')" />
          </a-card>
        </a-col>
        <a-col :xs="24" :lg="12">
          <a-card :bordered="false" :title="t('md.result.charts.rmsf')" size="small">
            <md-echart v-if="rmsfOption" :option="rmsfOption" />
            <a-empty v-else :description="t('md.result.chartEmpty')" />
          </a-card>
        </a-col>
        <a-col :xs="24" :lg="12">
          <a-card :bordered="false" :title="t('md.result.charts.rg')" size="small">
            <md-echart v-if="rgOption" :option="rgOption" />
            <a-empty v-else :description="t('md.result.chartEmpty')" />
          </a-card>
        </a-col>
        <a-col :xs="24" :lg="12">
          <a-card :bordered="false" :title="t('md.result.charts.temperature')" size="small">
            <md-echart v-if="temperatureOption" :option="temperatureOption" />
            <a-empty v-else :description="t('md.result.chartEmpty')" />
          </a-card>
        </a-col>
      </a-row>

      <a-row :gutter="16" class="md-result__grid">
        <a-col :xs="24" :lg="12">
          <a-card :bordered="false" :title="t('md.result.outputs')" size="small">
            <a-space direction="vertical" fill>
              <a-button
                block
                :disabled="!trajectoryFile"
                data-testid="md-download-trajectory"
                @click="downloadRole('trajectory_dcd')"
              >
                {{ t('md.result.downloadTrajectory') }}
              </a-button>
              <a-button
                block
                :disabled="!analysisFile"
                data-testid="md-download-analysis"
                @click="downloadRole('analysis_csv')"
              >
                {{ t('md.result.downloadAnalysis') }}
              </a-button>
              <a-button
                block
                :disabled="!topologyFile"
                data-testid="md-download-topology"
                @click="downloadRole('topology_pdb')"
              >
                {{ t('md.result.downloadTopology') }}
              </a-button>
              <a-button block :disabled="!metadataFile" @click="downloadRole('metadata_json')">
                {{ t('md.result.downloadMetadata') }}
              </a-button>
            </a-space>
            <a-alert
              type="warning"
              show-icon
              class="md-result__notice"
              :message="t('md.result.trajectoryNotice')"
            />
          </a-card>
        </a-col>
        <a-col :xs="24" :lg="12">
          <a-card :bordered="false" :title="t('md.result.structurePreview')" size="small">
            <div class="md-result__viewer">
              <structure-artifact-preview
                v-if="artifact && topologyFile"
                :artifact="artifact"
                :preferred-file-roles="['topology_pdb']"
              />
              <a-empty v-else :description="t('md.result.noTopology')" />
            </div>
            <p class="md-result__viewer-note">{{ t('md.result.staticPreviewNote') }}</p>
          </a-card>
        </a-col>
      </a-row>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import type { EChartsOption } from 'echarts'
  import Papa from 'papaparse'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import AppDescriptionList from '@/components/common/AppDescriptionList.vue'
  import StructureArtifactPreview from '@/components/artifacts/StructureArtifactPreview.vue'
  import MdEchart from './MdEchart.vue'
  import { getArtifactDetail, getMdResult } from '@/api/md'
  import { getTaskDetail } from '@/api/tasks'
  import { openTaskEventStream } from '@/api/task-events'
  import { fetchProtectedFileText, triggerProtectedFileDownload } from '@/utils/protected-file-access'
  import { buildAnalysisRows, downsampleSeries, findOutputByStandardType } from './analysis'
  import type { DescriptionSection } from '@/components/common/AppDescriptionList.vue'
  import type { ArtifactVersionFile, TypedArtifact } from '@/types/artifacts'
  import type { MdAnalysisRow, MdResultDetail, MdTrajectoryMetadata, MdTrajectoryRole } from '@/types/md'
  import type { Task } from '@/types/models'

  interface PapaParseResult {
    data: Array<Record<string, string>>
  }

  const { t } = useI18n()
  const route = useRoute()
  const taskId = computed(() => String(route.params.id ?? ''))

  const result = ref<MdResultDetail | null>(null)
  const task = ref<Task | null>(null)
  const artifact = ref<TypedArtifact | null>(null)
  const analysisRows = ref<MdAnalysisRow[]>([])
  const metadata = ref<MdTrajectoryMetadata>({})

  const loading = ref(false)
  const loadError = ref('')
  const progressPercent = ref(0)
  const progressMessage = ref('')
  let streamHandle: { close: () => void } | null = null

  const files = computed<ArtifactVersionFile[]>(() => artifact.value?.latest_version.files ?? [])

  function roleFile(role: MdTrajectoryRole): ArtifactVersionFile | null {
    return files.value.find((file) => file.role === role) ?? null
  }

  const analysisFile = computed(() => roleFile('analysis_csv'))
  const metadataFile = computed(() => roleFile('metadata_json'))
  const topologyFile = computed(() => roleFile('topology_pdb'))
  const trajectoryFile = computed(() => roleFile('trajectory_dcd'))

  const status = computed(() => result.value?.status ?? task.value?.status ?? '')
  const isRunning = computed(() => status.value === 'running' || status.value === 'pending' || status.value === 'queued')
  const statusColor = computed(() => {
    switch (status.value) {
      case 'success':
        return 'green'
      case 'running':
        return 'blue'
      case 'failure':
        return 'red'
      case 'canceled':
        return 'orange'
      default:
        return 'default'
    }
  })

  const totalFrames = computed(() => {
    const fromMeta = Number(metadata.value.total_frames)
    if (Number.isFinite(fromMeta) && fromMeta > 0) return Math.round(fromMeta)
    return analysisRows.value.length > 0 ? analysisRows.value.length : null
  })
  const currentFrame = computed(() => {
    if (!totalFrames.value) return 0
    return Math.min(totalFrames.value, Math.round((totalFrames.value * progressPercent.value) / 100))
  })

  function parseCsv(text: string): Array<Record<string, string>> {
    const parser = Papa as unknown as { parse: (input: string, config: Record<string, unknown>) => PapaParseResult }
    return parser.parse(text, { header: true, skipEmptyLines: true }).data
  }

  function lineOption(x: number[], y: number[], yName: string): EChartsOption {
    return {
      grid: { left: 48, right: 16, top: 24, bottom: 36 },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'value', name: t('md.result.chartXAxis'), nameLocation: 'middle', nameGap: 24 },
      yAxis: { type: 'value', name: yName },
      series: [{ type: 'line', smooth: true, showSymbol: false, data: x.map((value, index) => [value, y[index]]) }]
    }
  }

  function buildChartOption(field: keyof MdAnalysisRow, yName: string): EChartsOption | null {
    const rows = analysisRows.value.filter((row) => typeof row[field] === 'number')
    if (rows.length === 0) return null
    const sampled = downsampleSeries(rows, 600)
    const x = sampled.map((row) => row.time_ps)
    const y = sampled.map((row) => Number(row[field]))
    return lineOption(x, y, yName)
  }

  const rmsdOption = computed(() => buildChartOption('rmsd_nm', 'RMSD (nm)'))
  const rmsfOption = computed(() => buildChartOption('rmsf_nm', 'RMSF (nm)'))
  const rgOption = computed(() => buildChartOption('rg_nm', 'Rg (nm)'))
  const temperatureOption = computed(() => buildChartOption('temperature_k', 'T (K)'))

  async function loadAnalysisAndMetadata(): Promise<void> {
    if (analysisFile.value) {
      try {
        const text = await fetchProtectedFileText(analysisFile.value.download_url)
        analysisRows.value = buildAnalysisRows(parseCsv(text) as Array<Record<string, unknown>>)
      } catch {
        analysisRows.value = []
      }
    }
    if (metadataFile.value) {
      try {
        const text = await fetchProtectedFileText(metadataFile.value.download_url)
        const parsed = JSON.parse(text) as Record<string, unknown>
        metadata.value = parsed as MdTrajectoryMetadata
      } catch {
        metadata.value = {}
      }
    }
  }

  function startStream(): void {
    if (streamHandle) return
    const handle = openTaskEventStream(taskId.value, {
      onProgress: (payload) => {
        progressPercent.value = Math.max(0, Math.min(100, Math.round(payload.progress)))
        progressMessage.value = payload.progressMessage ?? ''
      },
      onStatus: (payload) => {
        progressPercent.value = Math.max(0, Math.min(100, Math.round(payload.progress)))
        progressMessage.value = payload.progressMessage ?? ''
        if (payload.status) {
          if (result.value) result.value.status = payload.status
        }
        if (payload.terminal) {
          stopStream()
          void reload()
        }
      },
      onDone: () => {
        stopStream()
        void reload()
      }
    })
    streamHandle = handle.available ? handle : null
  }

  function stopStream(): void {
    streamHandle?.close()
    streamHandle = null
  }

  async function reload(): Promise<void> {
    if (!taskId.value) return
    loading.value = true
    loadError.value = ''
    try {
      const [detail, taskDetail] = await Promise.all([
        getMdResult(taskId.value),
        getTaskDetail(taskId.value).catch(() => null)
      ])
      result.value = detail
      task.value = taskDetail?.data ?? null
      progressPercent.value = Math.round(taskDetail?.data.progress ?? 0)

      const output = findOutputByStandardType(detail.outputs, 'md_trajectory@1')
      if (output) {
        artifact.value = await getArtifactDetail(output.id)
        await loadAnalysisAndMetadata()
      } else {
        artifact.value = null
        analysisRows.value = []
      }

      if (isRunning.value) startStream()
      else stopStream()
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : String(error)
    } finally {
      loading.value = false
    }
  }

  async function downloadRole(role: MdTrajectoryRole): Promise<void> {
    const file = roleFile(role)
    if (!file) return
    await triggerProtectedFileDownload({ url: file.download_url, filename: file.filename ?? undefined })
  }

  onMounted(() => {
    void reload()
  })

  onBeforeUnmount(() => {
    stopStream()
  })

  const overviewSections = computed<DescriptionSection[]>(() => [
    {
      key: 'overview',
      fields: [
        { key: 'status', label: t('md.result.taskStatus'), value: result.value?.status ?? '-', tagColor: statusColor.value },
        { key: 'forceField', label: t('md.result.forceField'), value: metadata.value.force_field ?? '-' },
        { key: 'totalFrames', label: t('md.result.totalFrames'), value: totalFrames.value != null ? String(totalFrames.value) : '-' },
        {
          key: 'duration',
          label: t('md.result.duration'),
          value: metadata.value.duration_ns != null ? `${metadata.value.duration_ns} ns` : '-',
          hint: t('md.result.hints.duration'),
        },
        {
          key: 'temperature',
          label: t('md.result.temperature'),
          value: metadata.value.temperature_k != null ? `${metadata.value.temperature_k} K` : '-',
          hint: t('md.result.hints.temperature'),
        },
        {
          key: 'timestep',
          label: t('md.result.timestep'),
          value: metadata.value.timestep_ps != null ? `${metadata.value.timestep_ps} ps` : '-',
          hint: t('md.result.hints.timestep'),
        },
      ],
    },
  ])
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .md-result {
    max-width: @container-xxl;
    margin: 0 auto;
  }

  .md-result__overview {
    margin-bottom: @spacing-md;
    border-radius: @border-radius-lg;
  }

  .md-result__progress {
    margin-top: @spacing-md;
  }

  .md-result__progress-text {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .md-result__grid {
    margin-bottom: @spacing-sm;
  }

  .md-result__notice {
    margin-top: @spacing-md;
  }

  .md-result__viewer {
    height: 360px;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    overflow: hidden;
  }

  .md-result__viewer-note {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }
</style>
