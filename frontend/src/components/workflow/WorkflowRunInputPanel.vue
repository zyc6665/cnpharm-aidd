<template>
  <div v-if="requirements.length > 0" class="workflow-run-input-panel">
    <div class="run-input-header">
      <span>{{ t('workflow.templates.requiredInputs') }}</span>
      <a-button
        size="small"
        :disabled="autoFillDisabled"
        @click="emit('auto-fill')"
      >
        {{ t('workflow.templates.autoFillInputs') }}
      </a-button>
    </div>
    <div class="run-input-grid">
      <label
        v-for="semanticType in requirements"
        :key="semanticType"
        class="run-input-field"
      >
        <span>{{ semanticType }}</span>
        <a-select
          :value="selections[semanticType]"
          :options="resolveOptions(semanticType)"
          :placeholder="t('workflow.templates.selectInputArtifact')"
          :loading="loading"
          allow-clear
          show-search
          option-filter-prop="label"
          @change="emit('select', semanticType, $event)"
        />
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  requirements: string[]
  selections: Record<string, string | undefined>
  optionsBySemanticType: Record<string, Array<{ value: string; label: string }>>
  loading?: boolean
  autoFillDisabled?: boolean
}>()

const emit = defineEmits<{
  'auto-fill': []
  select: [semanticType: string, artifactId: string | undefined]
}>()

const { t } = useI18n()

function resolveOptions(semanticType: string) {
  return props.optionsBySemanticType[semanticType] ?? []
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workflow-run-input-panel {
  padding: @spacing-md;
  margin-bottom: @spacing-md;
  border: 1px solid @border-color-hover;
  border-radius: @border-radius-md;
  background: @bg-surface;
  box-shadow: @shadow-sm;
}

.run-input-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-sm;
  margin-bottom: @spacing-sm;
}

.run-input-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: @spacing-sm;
}

.run-input-field {
  display: grid;
  gap: @spacing-xs;

  span {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    font-weight: 600;
  }
}
</style>
