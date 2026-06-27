<template>
  <div class="workflow-template-toolbar">
    <a-input
      :value="name"
      class="workflow-name-input"
      :placeholder="t('workflow.templates.namePlaceholder')"
      @update:value="emit('update:name', $event)"
    />
    <a-select
      class="workflow-load-select"
      :value="selectedTemplateId"
      :placeholder="t('workflow.templates.loadPlaceholder')"
      :options="templateOptions"
      :loading="loading"
      allow-clear
      @change="emit('select-template', $event)"
    />
    <a-space size="small" wrap>
      <a-button @click="emit('new')">
        {{ t('workflow.templates.new') }}
      </a-button>
      <a-button
        type="primary"
        :loading="saving"
        @click="emit('save')"
      >
        {{ t('workflow.templates.save') }}
      </a-button>
      <a-button
        :disabled="!selectedTemplateId"
        :loading="saving"
        @click="emit('duplicate')"
      >
        {{ t('workflow.templates.duplicate') }}
      </a-button>
      <a-popconfirm
        :title="t('workflow.templates.deleteConfirm')"
        :ok-text="t('common.delete')"
        :cancel-text="t('common.cancel')"
        placement="bottomRight"
        @confirm="emit('delete')"
      >
        <a-button
          danger
          :disabled="!selectedTemplateId"
          :loading="saving"
        >
          {{ t('workflow.templates.delete') }}
        </a-button>
      </a-popconfirm>
      <a-button
        :disabled="runDisabled"
        :loading="running"
        @click="emit('run')"
      >
        {{ t('workflow.templates.run') }}
      </a-button>
    </a-space>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  name: string
  selectedTemplateId?: string | null
  templateOptions: Array<{ value: string; label: string }>
  loading?: boolean
  saving?: boolean
  running?: boolean
  runDisabled?: boolean
}>()

const emit = defineEmits<{
  'update:name': [value: string]
  'select-template': [value: string | undefined]
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

.workflow-template-toolbar {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: @spacing-md;
  margin-bottom: @spacing-md;
  border: 1px solid @border-color-hover;
  border-radius: @border-radius-md;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: @shadow-sm;
}

.workflow-name-input {
  width: min(280px, 100%);
}

.workflow-load-select {
  width: min(320px, 100%);
}

@media (max-width: @screen-md) {
  .workflow-template-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .workflow-name-input,
  .workflow-load-select {
    width: 100%;
  }
}
</style>
