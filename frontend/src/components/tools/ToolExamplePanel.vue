<template>
  <section v-if="example" class="example-panel">
    <div class="example-panel-header">
      <div class="example-panel-title-block">
        <span class="example-panel-kicker">{{ t('tools.exampleInput') }}</span>
        <strong class="example-panel-title">{{ example.name }}</strong>
        <span class="example-panel-description">
          {{ example.description || t('tools.exampleHint') }}
        </span>
      </div>
      <a-space wrap>
        <a-button v-if="example.input_files.length" @click="expanded = !expanded">
          <EyeOutlined />
          {{ expanded ? t('tools.hideExample') : t('tools.viewExample') }}
        </a-button>
        <a-button type="primary" :loading="applying" @click="$emit('use-example')">
          <ThunderboltOutlined />
          {{ t('tools.useExample') }}
        </a-button>
      </a-space>
    </div>

    <div v-if="expanded && example.input_files.length" class="example-panel-body">
      <div class="example-files">
        <span class="example-section-label">{{ t('tools.exampleFiles') }}</span>
        <div class="example-file-list">
          <button
            v-for="file in example.input_files"
            :key="file.field"
            type="button"
            class="example-file-item"
            :disabled="!file.exists || !file.previewable"
            @click="$emit('preview-file', file.field)"
          >
            <FileTextOutlined />
            <span class="example-file-name">{{ file.filename }}</span>
            <a-tag v-if="!file.exists" color="red">{{ t('tools.exampleFileMissing') }}</a-tag>
            <a-tag v-else-if="file.previewable" color="blue">{{ t('tools.preview') }}</a-tag>
            <a-tag v-else>{{ t('tools.previewUnavailable') }}</a-tag>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { ref } from 'vue'
  import { useI18n } from 'vue-i18n'
  import {
    EyeOutlined,
    FileTextOutlined,
    ThunderboltOutlined
  } from '@ant-design/icons-vue'
  import type { ToolExample } from '@/types/models'

  const props = defineProps<{
    example: ToolExample | null
    applying?: boolean
  }>()

  defineEmits<{
    'use-example': []
    'preview-file': [field: string]
  }>()

  const { t } = useI18n()
  const expanded = ref(false)
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .example-panel {
    border: 1px solid @border-color;
    background: @bg-hover;
    border-radius: @border-radius-lg;
    padding: @spacing-lg;
    margin-bottom: @spacing-lg;
  }

  .example-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: @spacing-lg;
    flex-wrap: wrap;
  }

  .example-panel-title-block {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 240px;
    flex: 1;
  }

  .example-panel-kicker {
    color: @accent-color;
    font-size: @font-size-xs;
    font-weight: @font-weight-semibold;
  }

  .example-panel-title {
    color: @text-color-light;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
  }

  .example-panel-description {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .example-panel-body {
    display: grid;
    gap: @spacing-md;
    margin-top: @spacing-md;
  }

  .example-section-label {
    display: block;
    margin-bottom: @spacing-xs;
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: @font-weight-semibold;
  }

  .example-file-list {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-sm;
  }

  .example-file-item {
    display: inline-flex;
    align-items: center;
    gap: @spacing-xs;
    min-height: 32px;
    max-width: 100%;
    padding: 4px 8px;
    border: 1px solid #d6e4ff;
    border-radius: @border-radius-base;
    background: @bg-elevated;
    color: @text-color-light;
    cursor: pointer;

    &:disabled {
      cursor: not-allowed;
      color: @text-color-light-tertiary;
      background: @bg-hover;
      border-color: @border-color;
    }
  }

  .example-file-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 260px;
  }

  @media (max-width: @screen-md) {
    .example-panel {
      padding: @spacing-md;
    }

    .example-panel-header {
      align-items: stretch;
    }

    :deep(.ant-space),
    :deep(.ant-btn) {
      width: 100%;
    }
  }
</style>
