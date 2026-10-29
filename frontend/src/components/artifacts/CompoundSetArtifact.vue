<template>
  <section class="compound-set-artifact" data-testid="compound-set-artifact">
    <a-alert type="info" show-icon :message="t('artifactAssets.compoundSet.notice')" />
    <FileArtifact :artifact="artifact" />

    <table class="asset-file-table" data-testid="compound-set-file-table">
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

    <div>
      <router-link :to="`/projects/${artifact.project_id}/candidates`">
        <a-button size="small" data-testid="compound-set-open-candidates">
          {{ t('artifactAssets.compoundSet.openCandidates') }}
        </a-button>
      </router-link>
    </div>
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

.compound-set-artifact {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
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
