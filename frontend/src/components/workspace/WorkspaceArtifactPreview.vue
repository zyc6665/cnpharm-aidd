<template>
  <a-drawer
    :open="open"
    :title="drawerTitle"
    :width="760"
    placement="right"
    @close="closeDrawer"
  >
    <div class="artifact-preview" data-testid="artifact-preview-drawer">
      <header class="artifact-preview__header">
        <div class="artifact-preview__heading">
          <strong class="artifact-preview__title">{{ drawerTitle }}</strong>
          <span class="artifact-preview__hint">{{ t('workspace.artifactPreviewHint') }}</span>
        </div>
        <div class="artifact-preview__actions">
          <a-button
            type="primary"
            :disabled="!downloadUrl"
            data-testid="artifact-preview-download"
            @click="download"
          >
            <template #icon><DownloadOutlined /></template>
            {{ t('common.download') }}
          </a-button>
        </div>
      </header>

      <dl v-if="row" class="artifact-preview__meta">
        <div>
          <dt>{{ t('workspace.artifactPreviewTypeLabel') }}</dt>
          <dd>{{ row.typeLabel }}</dd>
        </div>
        <div v-if="row.fileName">
          <dt>{{ t('tasks.filePreviewFile') }}</dt>
          <dd class="mono-cell">{{ row.fileName }}</dd>
        </div>
        <div>
          <dt>{{ t('workspace.artifactPreviewSizeLabel') }}</dt>
          <dd>{{ formatBytes(row.sizeBytes) }}</dd>
        </div>
        <div>
          <dt>{{ t('workspace.artifactPreviewUpdatedLabel') }}</dt>
          <dd>{{ formatTime(row.updatedAt) }}</dd>
        </div>
      </dl>

      <a-spin :spinning="loading">
        <div data-testid="artifact-preview-body" class="artifact-preview__body">
          <div v-if="error" class="artifact-preview__state artifact-preview__state--error" data-testid="artifact-preview-load-failed">
            <strong>{{ t('workspace.artifactPreviewLoadFailed') }}</strong>
            <span>{{ error }}</span>
          </div>

          <div
            v-else-if="previewKind === 'too-large'"
            class="artifact-preview__state"
            data-testid="artifact-preview-too-large"
          >
            <strong>{{ t('workspace.artifactPreviewTooLarge') }}</strong>
            <span>{{ t('workspace.artifactPreviewTooLargeHint', { size: formatBytes(row?.sizeBytes ?? 0) }) }}</span>
          </div>

          <CsvResultViewer
            v-else-if="previewKind === 'csv' && previewFile"
            :file="previewFile"
            data-testid="artifact-preview-csv"
          />

          <ArtifactRenderer
            v-else-if="previewKind === 'structure' && detail"
            :artifact="detail"
            data-testid="artifact-preview-structure"
          />

          <MoleculeViewer
            v-else-if="previewKind === 'structure' && scene"
            :scene="scene"
            data-testid="artifact-preview-structure"
          />

          <ResultFilePreview
            v-else-if="isFilePreviewKind && previewFile"
            :file="previewFile"
            :preview-kind="filePreviewKindForResult"
            data-testid="artifact-preview-file"
          />

          <div
            v-else-if="previewKind === 'download'"
            class="artifact-preview__state"
            data-testid="artifact-preview-unavailable"
          >
            <strong>{{ t('workspace.artifactPreviewUnavailable') }}</strong>
            <span>{{ t('workspace.artifactPreviewUnavailableHint') }}</span>
          </div>

          <div v-else class="artifact-preview__state" data-testid="artifact-preview-empty">
            {{ t('workspace.artifactPreviewEmpty') }}
          </div>
        </div>
      </a-spin>
    </div>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { DownloadOutlined } from '@ant-design/icons-vue'

import { buildArtifactVersionDownloadUrl, getArtifact } from '@/api/artifacts'
import type { WorkspaceArtifact, WorkspaceLegacyFile } from '@/api/workspace'
import { formatBytes } from '@/domain/common/format'
import type { RecentWorkspaceArtifactRow } from '@/domain/workspace'
import { formatWorkspaceTime } from '@/domain/workspace'
import {
  buildVisualizationResultItems,
  createVisualizationScene,
  detectCsvResultFile,
  detectVisualizationFormat,
  type TaskFileReference,
  type VisualizationFilePreviewKind,
  type VisualizationScene
} from '@/domain/tasks'
import type { Task } from '@/types/models'
import type { TypedArtifact } from '@/types/artifacts'
import { triggerProtectedFileDownload } from '@/utils/protected-file-access'
import CsvResultViewer from '@/components/tasks/CsvResultViewer.vue'
import ResultFilePreview from '@/components/tasks/ResultFilePreview.vue'
import ArtifactRenderer from '@/components/artifacts/ArtifactRenderer.vue'

/** 在线预览上限：超过此大小只显示元信息并提示下载，避免把大文件读进内存。 */
const MAX_PREVIEW_BYTES = 5 * 1024 * 1024

const MoleculeViewer = defineAsyncComponent(() => import('@/components/tasks/MoleculeViewer.vue'))

type PreviewKind = 'csv' | 'structure' | 'json' | 'text' | 'image' | 'download' | 'too-large' | 'empty'

const props = defineProps<{
  open: boolean
  row: RecentWorkspaceArtifactRow | null
  artifact?: WorkspaceArtifact | null
  legacyFile?: WorkspaceLegacyFile | null
}>()

const emit = defineEmits<{ 'update:open': [boolean] }>()

const { t } = useI18n()

const loading = ref(false)
const error = ref('')
const detail = ref<TypedArtifact | null>(null)
const previewFile = ref<TaskFileReference | null>(null)
const previewKind = ref<PreviewKind>('empty')
const scene = ref<VisualizationScene | null>(null)

const drawerTitle = computed(() => props.row?.title || t('workspace.artifactPreviewTitle'))
const downloadUrl = computed(() => previewFile.value?.url || props.row?.downloadUrl || '')
const isFilePreviewKind = computed(
  () => previewKind.value === 'json' || previewKind.value === 'text' || previewKind.value === 'image'
)
const filePreviewKindForResult = computed<VisualizationFilePreviewKind>(() =>
  previewKind.value === 'json' || previewKind.value === 'text' || previewKind.value === 'image'
    ? previewKind.value
    : 'download'
)
const formatTime = formatWorkspaceTime

function closeDrawer() {
  emit('update:open', false)
}

function pickPrimaryFile(artifact: TypedArtifact): TaskFileReference | null {
  const version = artifact.latest_version
  const files = [...(version.files ?? [])]
    .filter(file => Boolean(file.download_url))
    .sort((left, right) => left.sort_order - right.sort_order)
  const primary = files.find(file => file.is_primary) || files[0]
  if (primary) {
    return {
      id: primary.file_id || version.id,
      filename: primary.filename || version.filename,
      original_name: primary.filename || version.filename,
      content_type: primary.content_type || version.content_type || undefined,
      size: primary.size_bytes || version.size_bytes,
      url: primary.download_url
    }
  }
  return {
    id: version.id,
    filename: version.filename,
    content_type: version.content_type || undefined,
    size: version.size_bytes,
    url: buildArtifactVersionDownloadUrl(artifact.id, version.id)
  }
}

function resolveStructureScene(file: TaskFileReference, artifactType?: string) {
  const format = detectVisualizationFormat(file)
  if (!format || !file.url) {
    return null
  }
  const extension = `.${format === 'mmcif' ? 'cif' : format}`
  return createVisualizationScene(
    [],
    [
      {
        key: `artifact-preview-${file.id ?? file.filename ?? 'file'}`,
        url: file.url,
        label: file.filename || file.original_name || 'structure',
        source: 'output',
        role: artifactType === 'protein_structure' ? 'receptor' : 'ligand',
        format,
        extension
      }
    ],
    []
  )
}

function classifyFile(file: TaskFileReference, artifactType?: string): PreviewKind {
  if (detectCsvResultFile(file)) {
    return 'csv'
  }
  if (detectVisualizationFormat(file)) {
    scene.value = resolveStructureScene(file, artifactType)
    return 'structure'
  }
  const name = (file.filename || file.original_name || file.url || '').toLowerCase()
  const contentType = (file.content_type || '').toLowerCase().split(';')[0]?.trim() || ''
  if (/\.(json|geojson|jsonl)$/.test(name) || contentType === 'application/json' || contentType.endsWith('+json')) {
    return 'json'
  }
  if (/\.(png|jpe?g|gif|webp|svg|bmp)$/.test(name) || contentType.startsWith('image/')) {
    return 'image'
  }
  if (/\.(txt|log|md|markdown|yaml|yml|xml|html?|tsv|sh|py|js|ts)$/.test(name) || contentType.startsWith('text/')) {
    return 'text'
  }
  return 'download'
}

async function resolvePreviewTarget(): Promise<{
  file: TaskFileReference | null
  artifactType?: string
  kind?: PreviewKind
}> {
  if (props.artifact) {
    try {
      const response = await getArtifact(props.artifact.id)
      const artifact = response.data
      detail.value = artifact
      const primary = pickPrimaryFile(artifact)
      const item = buildVisualizationResultItems({ artifacts: [artifact] } as unknown as Task)[0]
      if (item?.kind === 'csv' && item.file) {
        return { file: item.file, artifactType: artifact.artifact_type, kind: 'csv' }
      }
      if (item?.kind === 'structure' && item.entry) {
        scene.value = createVisualizationScene([], [item.entry], [])
        // 结构预览由 ArtifactRenderer / MoleculeViewer 渲染，这里仅用于大小判断与下载。
        return {
          file: primary ?? {
            id: item.entry.key,
            filename: item.entry.label,
            url: item.entry.url
          },
          artifactType: artifact.artifact_type,
          kind: 'structure'
        }
      }
      return { file: primary, artifactType: artifact.artifact_type }
    } catch {
      // 详情接口失败时用总览行数据降级，仍可预览主文件
    }
    const version = props.artifact.latest_version
    return {
      file: {
        id: version.id,
        filename: version.filename,
        content_type: version.content_type || undefined,
        size: version.size_bytes,
        url: buildArtifactVersionDownloadUrl(props.artifact.id, version.id)
      },
      artifactType: props.artifact.artifact_type
    }
  }

  if (props.legacyFile) {
    const file = props.legacyFile
    return {
      file: {
        id: file.id,
        filename: file.filename,
        original_name: file.filename,
        content_type: file.content_type || undefined,
        size: file.size_bytes,
        url: `/api/v1/files/${file.id}/download`
      }
    }
  }

  return { file: null }
}

async function loadPreview() {
  loading.value = true
  error.value = ''
  detail.value = null
  previewFile.value = null
  scene.value = null
  previewKind.value = 'empty'
  try {
    const { file, artifactType, kind } = await resolvePreviewTarget()
    if (!file) {
      previewKind.value = 'empty'
      return
    }
    previewFile.value = file
    const gateSize = file.size ?? props.row?.sizeBytes
    if (gateSize && gateSize > MAX_PREVIEW_BYTES) {
      previewKind.value = 'too-large'
      return
    }
    previewKind.value = kind ?? classifyFile(file, artifactType)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    loading.value = false
  }
}

async function download() {
  if (!downloadUrl.value) {
    return
  }
  try {
    await triggerProtectedFileDownload({
      url: downloadUrl.value,
      filename: previewFile.value?.filename || props.row?.fileName || undefined
    })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }
}

watch(
  () => [props.open, props.row?.id, props.artifact?.id, props.legacyFile?.id],
  ([open]) => {
    if (open) {
      void loadPreview()
    }
  },
  { immediate: true }
)
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.artifact-preview {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
}

.artifact-preview__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: @spacing-md;
}

.artifact-preview__heading {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.artifact-preview__title {
  color: @text-primary;
  font-size: @font-size-lg;
  overflow-wrap: anywhere;
}

.artifact-preview__hint {
  margin-top: 4px;
  color: @text-tertiary;
  font-size: @font-size-xs;
}

.artifact-preview__meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: @spacing-sm @spacing-lg;
  margin: 0;
  padding: @spacing-sm @spacing-md;
  border: 1px solid @border-color;
  border-radius: @border-radius-md;
  background: @bg-hover;

  dt {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  dd {
    margin: 2px 0 0;
    color: @text-primary;
    font-size: @font-size-sm;
    overflow-wrap: anywhere;
  }
}

.artifact-preview__body {
  min-height: 240px;
}

.artifact-preview__state {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  min-height: 200px;
  padding: @spacing-lg;
  border: 1px dashed @border-color-hover;
  border-radius: @border-radius-md;
  color: @text-secondary;
  background: @bg-hover;
}

.artifact-preview__state--error {
  border-color: @error-color;
  color: @error-color;
  background: @error-color-light;
}

.mono-cell {
  font-family: @font-family-mono;
}
</style>
