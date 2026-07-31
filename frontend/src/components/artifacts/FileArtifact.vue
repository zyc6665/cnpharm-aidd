<template>
  <section class="artifact-card" data-testid="file-artifact">
    <div class="artifact-card__header">
      <div>
        <p class="artifact-card__eyebrow">{{ artifact.semantic_type }}</p>
        <h4>{{ artifact.name }}</h4>
      </div>
      <a-tag>{{ extensionLabel }}</a-tag>
    </div>

    <p v-if="artifact.description" class="artifact-card__description">{{ artifact.description }}</p>

    <a-descriptions :column="1" size="small" class="artifact-card__meta">
      <a-descriptions-item label="文件名">{{ version.filename }}</a-descriptions-item>
      <a-descriptions-item label="大小">{{ fileSize }}</a-descriptions-item>
      <a-descriptions-item label="SHA-256">{{ version.sha256 }}</a-descriptions-item>
    </a-descriptions>

    <a
      class="artifact-card__download"
      data-testid="artifact-download-link"
      :href="downloadUrl"
      @click.prevent="download"
    >
      下载文件
    </a>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { message } from 'ant-design-vue'
import { buildArtifactVersionDownloadUrl } from '@/api/artifacts'
import type { TypedArtifact } from '@/types/artifacts'
import { triggerProtectedFileDownload } from '@/utils/protected-file-access'

const props = defineProps<{
  artifact: TypedArtifact
}>()

const version = computed(() => props.artifact.latest_version)
const downloadUrl = computed(() => buildArtifactVersionDownloadUrl(props.artifact.id, version.value.id))
const extensionLabel = computed(() => {
  const match = version.value.filename.match(/\.([a-z0-9]+)$/i)
  return match?.[1]?.toUpperCase() || 'FILE'
})
const fileSize = computed(() => {
  const bytes = version.value.size_bytes
  if (!bytes) {
    return '0 B'
  }

  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`
})

async function download() {
  try {
    await triggerProtectedFileDownload({
      url: downloadUrl.value,
      filename: version.value.filename,
    })
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.artifact-card {
  display: flex;
  flex-direction: column;
  gap: @spacing-sm;
  padding: @spacing-md;
  border: 1px solid @border-color;
  border-radius: @border-radius-md;
  background: @bg-elevated;
}

.artifact-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: @spacing-md;
}

.artifact-card__header h4 {
  margin: 2px 0 0;
  color: @text-primary;
}

.artifact-card__eyebrow {
  margin: 0;
  color: @text-tertiary;
  font-size: @font-size-sm;
}

.artifact-card__description {
  margin: 0;
  color: @text-secondary;
}

.artifact-card__meta :deep(.ant-descriptions-item-label) {
  width: 86px;
}

.artifact-card__download {
  width: fit-content;
  color: @accent-color;
  font-weight: @font-weight-medium;
}
</style>
