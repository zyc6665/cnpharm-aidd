<template>
  <div v-if="visibleEntries.length" class="model-parameter-form" data-testid="model-parameter-form">
    <a-form layout="vertical">
      <a-row v-if="primaryEntries.length" :gutter="[12, 0]">
        <a-col
          v-for="[key, property] in primaryEntries"
          :key="key"
          :xs="24"
          :sm="fieldSpan(key, property)"
        >
          <ModelParameterField
            :field-key="key"
            :property="property"
            :value="modelValue[key]"
            :required="isRequired(schema, key)"
            :disabled="disabled"
            :readonly="Boolean(overrides[key]?.readonly)"
            @update="(value: ParameterValue) => updateValue(key, value)"
          />
        </a-col>
      </a-row>

      <a-collapse
        v-if="advancedEntries.length"
        ghost
        class="model-parameter-form__advanced"
        data-testid="model-parameter-advanced"
      >
        <a-collapse-panel key="advanced" :header="t('design.molecule.advancedParams')">
          <a-row :gutter="[12, 0]">
            <a-col
              v-for="[key, property] in advancedEntries"
              :key="key"
              :xs="24"
              :sm="fieldSpan(key, property)"
            >
              <ModelParameterField
                :field-key="key"
                :property="property"
                :value="modelValue[key]"
                :required="isRequired(schema, key)"
                :disabled="disabled"
                :readonly="Boolean(overrides[key]?.readonly)"
                @update="(value: ParameterValue) => updateValue(key, value)"
              />
            </a-col>
          </a-row>
        </a-collapse-panel>
      </a-collapse>
    </a-form>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ModelParameterField from './ModelParameterField.vue'
import {
  isRequired,
  schemaProperties,
  type ParameterValue
} from '@/domain/tools/parameterSchema'
import type { SchemaProperty, ToolSchema } from '@/types/models'

export interface ParameterFieldOverride {
  hidden?: boolean
  readonly?: boolean
  textarea?: boolean
  span?: number
}

const props = withDefaults(
  defineProps<{
    modelValue: Record<string, ParameterValue>
    schema?: ToolSchema | null
    disabled?: boolean
    overrides?: Record<string, ParameterFieldOverride>
    /**
     * 常用参数键：命中的参数直接展开，其余收进「高级参数」折叠面板。
     * 不传时保持旧行为——所有可见参数都直接展开。
     */
    primaryKeys?: string[]
  }>(),
  { schema: null, disabled: false, overrides: () => ({}), primaryKeys: () => [] }
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: Record<string, ParameterValue>): void
}>()

const { t } = useI18n()

const visibleEntries = computed(() =>
  schemaProperties(props.schema).filter(([key]) => !props.overrides[key]?.hidden && !props.schema?.properties[key]?.hidden)
)

const hasPrimaryGroups = computed(() => props.primaryKeys.length > 0)

const primaryEntries = computed(() => {
  if (!hasPrimaryGroups.value) return visibleEntries.value
  const keys = new Set(props.primaryKeys)
  return visibleEntries.value.filter(([key]) => keys.has(key))
})

const advancedEntries = computed(() => {
  if (!hasPrimaryGroups.value) return []
  const keys = new Set(props.primaryKeys)
  return visibleEntries.value.filter(([key]) => !keys.has(key))
})

function fieldSpan(key: string, property: SchemaProperty): number {
  const overrideSpan = props.overrides[key]?.span
  if (overrideSpan) return overrideSpan
  const format = property.format
  if (format === 'textarea' || format === 'fasta' || (property.maxLength ?? 0) >= 500 || key === 'sequence') {
    return 24
  }
  return 8
}

function updateValue(key: string, value: ParameterValue): void {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.model-parameter-form {
  :deep(.ant-form-item) {
    margin-bottom: @spacing-md;
  }

  :deep(.ant-form-item-extra) {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  &__advanced {
    margin-top: @spacing-xs;
  }
}
</style>
