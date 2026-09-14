<template>
  <a-modal
    v-model:open="previewModalOpen"
    :title="preview?.filename || t('tools.exampleFilePreview')"
    :footer="null"
    width="760px"
  >
    <SkeletonCard v-if="previewLoading" />
    <div v-else-if="preview" class="example-preview">
      <a-alert
        v-if="preview.truncated"
        type="info"
        show-icon
        :message="t('tools.previewTruncated')"
        style="margin-bottom: 12px"
      />
      <pre v-if="preview.previewable" class="example-preview-content">{{ preview.content }}</pre>
      <a-empty v-else :description="t('tools.previewUnavailable')" />
    </div>
  </a-modal>
  <a-modal
    v-model:open="documentationModalOpen"
    :title="t('tools.introduction')"
    :footer="null"
    width="860px"
    class="tool-documentation-modal"
  >
    <div class="tool-documentation-content" v-html="documentationHtml"></div>
  </a-modal>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import SkeletonCard from '@/components/common/SkeletonCard.vue'
  import type { ToolExampleFilePreview } from '@/types/models'

  const props = defineProps<{
    previewOpen: boolean
    documentationOpen: boolean
    previewLoading: boolean
    preview: ToolExampleFilePreview | null
    documentationHtml: string
  }>()

  const emit = defineEmits<{
    'update:previewOpen': [open: boolean]
    'update:documentationOpen': [open: boolean]
  }>()

  const { t } = useI18n()

  const previewModalOpen = computed({
    get: () => props.previewOpen,
    set: open => emit('update:previewOpen', open),
  })

  const documentationModalOpen = computed({
    get: () => props.documentationOpen,
    set: open => emit('update:documentationOpen', open),
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .example-preview-content {
    max-height: 520px;
    overflow: auto;
    margin: 0;
    padding: @spacing-md;
    border: 1px solid @border-color;
    border-radius: @border-radius-base;
    background: #0f172a;
    color: #e5e7eb;
    font-family: monospace;
    font-size: 12px;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .tool-documentation-content {
    max-height: 68vh;
    overflow: auto;
    color: @text-color-light-secondary;
    line-height: @line-height-loose;

    :deep(h1),
    :deep(h2),
    :deep(h3) {
      color: @text-color-light-primary;
      font-weight: @font-weight-semibold;
      margin: @spacing-lg 0 @spacing-sm;
    }

    :deep(h1) {
      margin-top: 0;
      font-size: 24px;
    }

    :deep(h2) {
      font-size: @font-size-lg;
    }

    :deep(h3) {
      font-size: @font-size-md;
    }

    :deep(p),
    :deep(ul),
    :deep(table),
    :deep(pre) {
      margin-bottom: @spacing-md;
    }

    :deep(ul) {
      padding-left: @spacing-xl;
    }

    :deep(table) {
      width: 100%;
      border-collapse: collapse;
      font-size: @font-size-sm;
    }

    :deep(th),
    :deep(td) {
      padding: 8px 10px;
      border: 1px solid @border-color;
      vertical-align: top;
    }

    :deep(th) {
      background: @bg-hover;
      color: @text-primary;
      font-weight: @font-weight-semibold;
    }

    :deep(code) {
      padding: 2px 5px;
      border-radius: 4px;
      background: @bg-hover;
      color: @text-secondary;
      font-family: monospace;
      font-size: 12px;
    }

    :deep(pre) {
      padding: @spacing-md;
      border-radius: @border-radius-base;
      background: @bg-body;
      border: 1px solid @border-color;
      overflow: auto;

      code {
        padding: 0;
        background: transparent;
        color: @text-primary;
      }
    }

    :deep(a) {
      color: @accent-color;
    }
  }
</style>
