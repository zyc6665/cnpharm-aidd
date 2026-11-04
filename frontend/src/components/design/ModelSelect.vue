<template>
  <div class="model-select" data-testid="model-select">
    <a-select
      v-if="options.length"
      :value="modelValue"
      :loading="loading"
      :disabled="disabled"
      :placeholder="t('design.modelSelect.placeholder')"
      class="model-select__control"
      data-testid="model-select-control"
      @change="handleChange"
    >
      <a-select-option
        v-for="option in options"
        :key="option.slug"
        :value="option.slug"
        :label="option.name"
      >
        {{ optionLabel(option) }}
      </a-select-option>
    </a-select>
    <a-input
      v-else
      :value="modelValue"
      :disabled="loading || disabled"
      :placeholder="t('design.modelSelect.placeholder')"
      class="model-select__control"
      data-testid="model-select-fallback"
      @update:value="handleChange"
    />
    <p v-if="options.length > 1" class="model-select__hint">{{ t('design.modelSelect.hint') }}</p>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ModelOption } from '@/composables/useModelOptions'

defineProps<{
  modelValue: string
  options: ModelOption[]
  loading?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>()
const { t } = useI18n()

function optionLabel(option: ModelOption): string {
  const version = option.version ? ` · v${option.version}` : ''
  const suffix = option.mock ? ` (${t('design.modelSelect.mock')})` : ''
  return `${option.name}${version}${suffix}`
}

function handleChange(value: unknown): void {
  if (typeof value === 'string') emit('update:modelValue', value)
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.model-select {
  .model-select__control {
    width: 100%;
  }

  .model-select__hint {
    margin: @spacing-xs 0 0;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }
}
</style>
