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

    <div
      v-if="deliveryMetadataEntries.length"
      class="artifact-card__delivery-metadata"
      data-testid="artifact-delivery-metadata"
    >
      <span class="artifact-card__metadata-title">交付元数据</span>
      <dl>
        <div v-for="entry in deliveryMetadataEntries" :key="entry.key">
          <dt>{{ entry.label }}</dt>
          <dd>{{ entry.value }}</dd>
        </div>
      </dl>
    </div>

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

    <div v-if="roleFiles.length" class="artifact-card__role-files">
      <span class="artifact-card__role-title">角色文件</span>
      <a
        v-for="file in roleFiles"
        :key="file.id"
        class="artifact-card__role-download"
        :data-testid="`artifact-role-download-link:${file.role}`"
        :href="file.download_url"
        @click.prevent="downloadRoleFile(file)"
      >
        <span>{{ file.role }}</span>
        <span>{{ file.filename || file.role }}</span>
      </a>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { message } from 'ant-design-vue'
import { buildArtifactVersionDownloadUrl } from '@/api/artifacts'
import type { ArtifactVersionFile, TypedArtifact } from '@/types/artifacts'
import { triggerProtectedFileDownload } from '@/utils/protected-file-access'
import { formatBytes } from '@/domain/common/format'

const props = defineProps<{
  artifact: TypedArtifact
}>()

const deliveryMetadataLabels: Record<string, string> = {
  model_version: '模型版本',
  runtime_ref: '运行环境',
  endpoint_ref: 'Endpoint',
  weights_ref: '权重',
  evidence_level: '证据等级',
  applicability_domain_status: '适用域',
  unit_or_label_policy: '单位/标签策略',
  model_card_ref: '模型卡',
  verification_record_ref: '验证记录'
}

const deliveryMetadataKeys = Object.keys(deliveryMetadataLabels)

const version = computed(() => props.artifact.latest_version)
const downloadUrl = computed(() => buildArtifactVersionDownloadUrl(props.artifact.id, version.value.id))
const roleFiles = computed(() =>
  [...(version.value.files ?? [])]
    .filter(file => Boolean(file.download_url))
    .sort((left, right) => left.sort_order - right.sort_order)
)
const extensionLabel = computed(() => {
  const match = version.value.filename.match(/\.([a-z0-9]+)$/i)
  return match?.[1]?.toUpperCase() || 'FILE'
})
const fileSize = computed(() => formatBytes(version.value.size_bytes ?? 0))
const deliveryMetadataEntries = computed(() => {
  const metadata = version.value.manifest_json?.metadata
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
    return []
  }

  return deliveryMetadataKeys.flatMap(key => {
    const value = metadata[key]
    if (value === null || value === undefined || value === '') {
      return []
    }

    return [
      {
        key,
        label: deliveryMetadataLabels[key],
        value: typeof value === 'object' ? JSON.stringify(value) : String(value)
      }
    ]
  })
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

async function downloadRoleFile(file: ArtifactVersionFile) {
  try {
    await triggerProtectedFileDownload({
      url: file.download_url,
      filename: file.filename || file.role,
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

.artifact-card__delivery-metadata {
  display: flex;
  flex-direction: column;
  gap: @spacing-xs;
  padding: @spacing-sm 0;
  border-top: 1px solid @border-color;
  border-bottom: 1px solid @border-color;

  dl {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    margin: 0;
  }

  div {
    display: grid;
    grid-template-columns: 112px minmax(0, 1fr);
    gap: @spacing-sm;
    font-size: @font-size-sm;
  }

  dt {
    color: @text-tertiary;
  }

  dd {
    margin: 0;
    color: @text-secondary;
    overflow-wrap: anywhere;
  }
}

.artifact-card__metadata-title {
  color: @text-tertiary;
  font-size: @font-size-xs;
}

.artifact-card__meta :deep(.ant-descriptions-item-label) {
  width: 86px;
}

.artifact-card__download {
  width: fit-content;
  color: @accent-color;
  font-weight: @font-weight-medium;
}

.artifact-card__role-files {
  display: flex;
  flex-direction: column;
  gap: @spacing-xs;
  padding-top: @spacing-sm;
  border-top: 1px solid @border-color;
}

.artifact-card__role-title {
  color: @text-tertiary;
  font-size: @font-size-xs;
}

.artifact-card__role-download {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-sm;
  color: @accent-color;
  font-size: @font-size-sm;
}

.artifact-card__role-download span:last-child {
  color: @text-secondary;
  overflow-wrap: anywhere;
}
</style>
