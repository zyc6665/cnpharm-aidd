<template>
  <div class="workflow-canvas-toolbar">
    <a-input
      :value="name"
      class="workflow-name-input"
      :placeholder="t('workflow.canvasPresets.namePlaceholder')"
      @update:value="emit('update:name', $event)"
    />
    <a-select
      class="workflow-load-select"
      :value="selectedCanvasPresetId"
      :placeholder="t('workflow.canvasPresets.loadPlaceholder')"
      :options="canvasPresetOptions"
      :loading="loading"
      allow-clear
      @change="emit('select-preset', $event)"
    />
    <a-space size="small" wrap>
      <a-button @click="emit('new')">
        {{ t('workflow.canvasPresets.new') }}
      </a-button>
      <a-button
        type="primary"
        :loading="saving"
        @click="emit('save')"
      >
        {{ t('workflow.canvasPresets.save') }}
      </a-button>
      <a-button
        :disabled="!selectedCanvasPresetId"
        :loading="saving"
        @click="emit('duplicate')"
      >
        {{ t('workflow.canvasPresets.duplicate') }}
      </a-button>
      <a-popconfirm
        :title="t('workflow.canvasPresets.deleteConfirm')"
        :ok-text="t('common.delete')"
        :cancel-text="t('common.cancel')"
        placement="bottomRight"
        @confirm="emit('delete')"
      >
        <a-button
          danger
          :disabled="!selectedCanvasPresetId"
          :loading="saving"
        >
          {{ t('workflow.canvasPresets.delete') }}
        </a-button>
      </a-popconfirm>
      <a-button
        :disabled="runDisabled"
        :loading="running"
        @click="emit('run')"
      >
        {{ t('workflow.canvasPresets.run') }}
      </a-button>
    </a-space>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  name: string
  selectedCanvasPresetId?: string | null
  canvasPresetOptions: Array<{ value: string; label: string }>
  loading?: boolean
  saving?: boolean
  running?: boolean
  runDisabled?: boolean
}>()

const emit = defineEmits<{
  'update:name': [value: string]
  'select-preset': [value: string | undefined]
  new: []
  save: []
  duplicate: []
  delete: []
  run: []
}>()

const { t } = useI18n()
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workflow-canvas-toolbar {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: @spacing-md;
  margin-bottom: @spacing-md;
  border: 1px solid @border-color-hover;
  border-radius: @border-radius-md;
  background: @bg-surface;
  box-shadow: @shadow-sm;
}

.workflow-name-input {
  width: min(280px, 100%);
}

.workflow-load-select {
  width: min(320px, 100%);
}

@media (max-width: @screen-md) {
  .workflow-canvas-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .workflow-name-input,
  .workflow-load-select {
    width: 100%;
  }
}
</style>
