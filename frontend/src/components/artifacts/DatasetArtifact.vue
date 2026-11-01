<template>
  <section class="dataset-artifact" data-testid="dataset-artifact">
    <a-alert type="info" show-icon :message="t('artifactAssets.dataset.notice')" />

    <dl class="dataset-artifact__summary">
      <div>
        <dt>{{ t('artifactAssets.dataset.name') }}</dt>
        <dd>{{ artifact.name }}</dd>
      </div>
      <div>
        <dt>{{ t('artifactAssets.dataset.type') }}</dt>
        <dd>{{ artifact.standard_type || artifact.semantic_type || artifact.artifact_type }}</dd>
      </div>
      <div>
        <dt>{{ t('artifactAssets.dataset.fileCount') }}</dt>
        <dd>{{ files.length }}</dd>
      </div>
      <div>
        <dt>{{ t('artifactAssets.createdAt') }}</dt>
        <dd>{{ artifact.created_at }}</dd>
      </div>
    </dl>

    <FileArtifact :artifact="artifact" />

    <table class="asset-file-table" data-testid="dataset-file-table">
      <thead>
        <tr>
          <th>{{ t('artifactAssets.fileRole') }}</th>
          <th>{{ t('artifactAssets.fileName') }}</th>
          <th>{{ t('artifactAssets.fileSize') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="file in files" :key="file.id">
          <td>{{ file.role }}</td>
          <td class="mono-cell">{{ file.filename || '-' }}</td>
          <td>{{ formatSize(file.size_bytes) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { TypedArtifact } from '@/types/artifacts'

import FileArtifact from './FileArtifact.vue'

const props = defineProps<{
  artifact: TypedArtifact
}>()

const { t } = useI18n()

const files = computed(() => props.artifact.latest_version.files || [])

function formatSize(sizeBytes?: number | null): string {
  if (sizeBytes === undefined || sizeBytes === null) {
    return '-'
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.dataset-artifact {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
}

.dataset-artifact__summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: @spacing-sm @spacing-lg;
  margin: 0;

  dt {
    color: @text-color-secondary;
    font-size: 12px;
  }

  dd {
    margin: 0;
  }
}

.asset-file-table {
  width: 100%;
  border-collapse: collapse;

  th,
  td {
    padding: 6px 8px;
    text-align: left;
    border-bottom: 1px solid @border-color-base;
  }
}
</style>
