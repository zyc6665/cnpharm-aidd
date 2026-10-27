<template>
  <div class="result-file-preview">
    <div class="result-file-preview__header">
      <div>
        <h5>{{ fileLabel }}</h5>
        <p>{{ fileMeta }}</p>
      </div>
      <button
        data-testid="file-preview-download"
        type="button"
        class="result-file-preview__download"
        @click="downloadFile"
      >
        {{ t('common.download') }}
      </button>
    </div>

    <div v-if="previewKind === 'download'" class="result-file-preview__download-only">
      <strong>{{ t('tasks.filePreviewDownloadOnly') }}</strong>
      <span>{{ t('tasks.filePreviewDownloadOnlyDesc') }}</span>
    </div>

    <div v-else-if="loading" data-testid="file-preview-loading" class="result-file-preview__state">
      {{ t('tasks.filePreviewLoading') }}
    </div>

    <div v-else-if="error" data-testid="file-preview-alert" class="result-file-preview__state result-file-preview__state--error">
      <strong>{{ t('tasks.filePreviewLoadFailed') }}</strong>
      <span>{{ error }}</span>
    </div>

    <div v-else-if="tooLarge" class="result-file-preview__state">
      <strong>{{ t('tasks.filePreviewTooLarge') }}</strong>
      <span>{{ t('tasks.filePreviewTooLargeDesc') }}</span>
    </div>

    <img
      v-else-if="previewKind === 'image' && previewUrl"
      data-testid="file-preview-image"
      class="result-file-preview__image"
      :src="previewUrl"
      :alt="fileLabel"
    />

    <pre
      v-else-if="previewKind === 'text' || previewKind === 'json'"
      data-testid="file-preview-text"
      class="result-file-preview__text"
    >{{ content }}</pre>

    <div v-else class="result-file-preview__state">
      {{ t('tasks.filePreviewEmpty') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { TaskFileReference, VisualizationFilePreviewKind } from '@/domain/tasks'
import { formatTaskFileSize } from '@/domain/tasks'
import {
  createProtectedObjectUrl,
  fetchProtectedFileText,
  triggerProtectedFileDownload
} from '@/utils/protected-file-access'

const MAX_PREVIEW_BYTES = 2 * 1024 * 1024

const props = defineProps<{
  file: TaskFileReference
  previewKind: VisualizationFilePreviewKind
}>()

const { t } = useI18n()
const loading = ref(false)
const error = ref('')
const content = ref('')
const previewUrl = ref('')
const tooLarge = ref(false)
let revokePreviewUrl: (() => void) | null = null

const fileLabel = computed(() => props.file.original_name || props.file.filename || t('tasks.filePreview'))
const fileMeta = computed(() => {
  const extension = props.file.filename?.split('.').pop()?.toUpperCase() || t('tasks.filePreviewFile')
  return `${extension} · ${formatTaskFileSize(props.file.size)}`
})

function cleanupPreviewUrl() {
  revokePreviewUrl?.()
  revokePreviewUrl = null
  previewUrl.value = ''
}

function formatJson(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return text
  }
}

async function loadPreview() {
  cleanupPreviewUrl()
  content.value = ''
  error.value = ''
  tooLarge.value = false

  if (props.previewKind === 'download') {
    return
  }

  if (!props.file.url) {
    error.value = t('tasks.filePreviewMissingUrl')
    return
  }

  if (props.file.size && props.file.size > MAX_PREVIEW_BYTES) {
    tooLarge.value = true
    return
  }

  loading.value = true
  try {
    if (props.previewKind === 'image') {
      const resource = await createProtectedObjectUrl(props.file.url)
      previewUrl.value = resource.url
      revokePreviewUrl = resource.revoke
      return
    }

    const text = await fetchProtectedFileText(props.file.url)
    content.value = props.previewKind === 'json' ? formatJson(text) : text
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    loading.value = false
  }
}

async function downloadFile() {
  try {
    await triggerProtectedFileDownload(props.file)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }
}

watch(
  () => `${props.file.id ?? props.file.filename ?? ''}:${props.file.url ?? ''}:${props.previewKind}`,
  () => {
    void loadPreview()
  },
  { immediate: true }
)

onUnmounted(() => {
  cleanupPreviewUrl()
})
</script>

<style scoped lang="less">
.result-file-preview {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 280px;
  padding: 18px;
  border: 1px solid @border-color;
  border-radius: @border-radius-lg;
  background: @bg-surface;
}

.result-file-preview__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.result-file-preview__header h5 {
  margin: 0 0 6px;
  color: @text-primary;
  font-size: @font-size-lg;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.result-file-preview__header p,
.result-file-preview__download-only span,
.result-file-preview__state span {
  margin: 0;
  color: @text-secondary;
  line-height: 1.6;
}

.result-file-preview__download {
  flex: 0 0 auto;
  padding: 6px 12px;
  border: 1px solid @accent-color-border;
  border-radius: @border-radius-md;
  color: @accent-color;
  background: @accent-color-light;
  cursor: pointer;
}

.result-file-preview__download:hover {
  background: @accent-color-border;
}

.result-file-preview__download-only,
.result-file-preview__state {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  min-height: 220px;
  padding: 20px;
  border: 1px dashed @border-color-hover;
  border-radius: @border-radius-lg;
  color: @text-secondary;
  background: @bg-hover;
}

.result-file-preview__state--error {
  border-color: @error-color;
  color: @error-color;
  background: @error-color-light;
}

.result-file-preview__text {
  max-height: 500px;
  margin: 0;
  padding: 16px;
  overflow: auto;
  border-radius: 12px;
  color: @text-primary;
  background: @bg-body;
  font: @font-size-xs/1.65 @font-family-mono, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.result-file-preview__image {
  display: block;
  width: 100%;
  max-height: 520px;
  object-fit: contain;
  border-radius: @border-radius-md;
  background: @bg-hover;
}
</style>
