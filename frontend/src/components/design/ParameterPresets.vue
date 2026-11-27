<template>
  <div class="parameter-presets" data-testid="parameter-presets">
    <div class="parameter-presets__row">
      <span class="parameter-presets__label">{{ t('design.presets.title') }}</span>
      <a-select
        :value="selectedPresetId"
        class="parameter-presets__select"
        :placeholder="t('design.presets.selectPlaceholder')"
        :disabled="disabled"
        :options="presetOptions"
        data-testid="parameter-preset-select"
        @change="handleSelect"
      />
      <a-button size="small" :disabled="disabled" data-testid="parameter-preset-save" @click="openSaveModal">
        {{ t('design.presets.saveCurrent') }}
      </a-button>
    </div>

    <div v-if="customPresets.length" class="parameter-presets__custom" data-testid="parameter-presets-custom">
      <a-tag
        v-for="preset in customPresets"
        :key="preset.id"
        closable
        class="parameter-presets__tag"
        :data-testid="`parameter-preset-tag-${preset.id}`"
        @click="handleSelect(preset.id)"
        @close.stop.prevent="removePreset(preset.id)"
      >
        {{ preset.name }}
      </a-tag>
    </div>

    <a-modal
      v-model:open="saveModalOpen"
      :title="t('design.presets.saveTitle')"
      :ok-text="t('design.presets.saveCurrent')"
      data-testid="parameter-preset-modal"
      @ok="saveCurrent"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('design.presets.name')" required>
          <a-input
            v-model:value="presetName"
            :placeholder="t('design.presets.namePlaceholder')"
            data-testid="parameter-preset-name"
            @press-enter="saveCurrent"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { ToolSchema } from '@/types/models'
import type { ParameterValues } from '@/domain/tools/parameterSchema'

interface BuiltInPreset {
  id: string
  nameKey: string
  params: ParameterValues
}

interface StoredPreset {
  id: string
  name: string
  params: ParameterValues
}

const props = withDefaults(
  defineProps<{
    schema?: ToolSchema | null
    values?: ParameterValues
    storageKey?: string
    disabled?: boolean
  }>(),
  {
    schema: null,
    values: () => ({}),
    storageKey: 'design:parameter-presets:molecule',
    disabled: false,
  }
)

const emit = defineEmits<{
  (event: 'load', params: ParameterValues): void
}>()

const { t } = useI18n()

/** 内置预设的取值直接对齐 pocket2mol 契约里的参数名。 */
const BUILT_IN_PRESETS: BuiltInPreset[] = [
  { id: 'quick', nameKey: 'design.presets.builtInPresets.quick', params: { num_samples: 20 } },
  { id: 'standard', nameKey: 'design.presets.builtInPresets.standard', params: { num_samples: 100 } },
  { id: 'fine', nameKey: 'design.presets.builtInPresets.fine', params: { num_samples: 300 } },
]

/**
 * 将内置预设的参数映射到当前 schema：Pocket2Mol 用 `num_samples`，LDDM 用 `n_samples`。
 * 如果 schema 定义了 `minimum`/`maximum`，自动钳位到范围内。
 */
function resolveBuiltInPresetParams(preset: BuiltInPreset, schema: ToolSchema | null): ParameterValues {
  const baseValue = preset.params.num_samples
  if (typeof baseValue !== 'number' || !Number.isFinite(baseValue)) return {}

  const schemaProps = schema?.properties ?? {}
  const result: ParameterValues = {}

  for (const key of ['num_samples', 'n_samples'] as const) {
    if (!(key in schemaProps)) continue
    const prop = schemaProps[key]
    const min = typeof prop?.minimum === 'number' ? prop.minimum : undefined
    const max = typeof prop?.maximum === 'number' ? prop.maximum : undefined
    let clamped = baseValue
    if (min !== undefined && clamped < min) clamped = min
    if (max !== undefined && clamped > max) clamped = max
    result[key] = clamped
  }

  return result
}

const selectedPresetId = ref<string | undefined>(undefined)
const saveModalOpen = ref(false)
const presetName = ref('')
const customPresets = ref<StoredPreset[]>(readCustomPresets())

watch(
  () => props.storageKey,
  () => {
    customPresets.value = readCustomPresets()
    selectedPresetId.value = undefined
  }
)

function schemaKeys(): Set<string> {
  return new Set(Object.keys(props.schema?.properties ?? {}))
}

function filterToSchema(params: ParameterValues): ParameterValues {
  const keys = schemaKeys()
  if (keys.size === 0) return { ...params }
  return Object.fromEntries(
    Object.entries(params).filter(([key]) => keys.has(key))
  ) as ParameterValues
}

function readCustomPresets(): StoredPreset[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(props.storageKey)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((item): item is StoredPreset => {
        if (!item || typeof item !== 'object') return false
        const candidate = item as Partial<StoredPreset>
        return (
          typeof candidate.id === 'string' &&
          typeof candidate.name === 'string' &&
          Boolean(candidate.params) &&
          typeof candidate.params === 'object'
        )
      })
      .map(item => ({ id: item.id, name: item.name, params: { ...item.params } }))
  } catch {
    return []
  }
}

function persistCustomPresets(): boolean {
  if (typeof localStorage === 'undefined') return false
  try {
    localStorage.setItem(props.storageKey, JSON.stringify(customPresets.value))
    return true
  } catch {
    // 存储不可用时保留内存中的修改，不阻断流程。
    return false
  }
}

const presetOptions = computed(() => [
  ...BUILT_IN_PRESETS.map(preset => ({
    label: `${t(preset.nameKey)} · ${t('design.presets.builtIn')}`,
    value: preset.id,
  })),
  ...customPresets.value.map(preset => ({
    label: `${preset.name} · ${t('design.presets.custom')}`,
    value: preset.id,
  })),
])

function handleSelect(value: unknown): void {
  if (typeof value !== 'string') return
  const builtIn = BUILT_IN_PRESETS.find(item => item.id === value)
  const custom = customPresets.value.find(item => item.id === value)
  selectedPresetId.value = undefined

  if (builtIn) {
    emit('load', filterToSchema(resolveBuiltInPresetParams(builtIn, props.schema)))
  } else if (custom) {
    emit('load', filterToSchema(custom.params))
  }
}

function openSaveModal(): void {
  presetName.value = ''
  saveModalOpen.value = true
}

function saveCurrent(): void {
  const name = presetName.value.trim()
  if (!name) {
    message.warning(t('design.presets.nameRequired'))
    return
  }
  const preset: StoredPreset = {
    id: `preset-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    name,
    params: filterToSchema(props.values),
  }
  customPresets.value = [...customPresets.value, preset]
  saveModalOpen.value = false
  if (persistCustomPresets()) message.success(t('design.presets.saved'))
  else message.warning(t('design.presets.savedSessionOnly'))
}

function removePreset(id: string): void {
  customPresets.value = customPresets.value.filter(preset => preset.id !== id)
  if (persistCustomPresets()) message.success(t('design.presets.deleted'))
  else message.warning(t('design.presets.deletedSessionOnly'))
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.parameter-presets {
  margin-bottom: @spacing-md;
  padding: @spacing-md;
  border: 1px dashed @border-color;
  border-radius: @border-radius-md;
  background: @surface-sunken;
}

.parameter-presets__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: @spacing-sm;
}

.parameter-presets__label {
  color: @text-secondary;
  font-size: @font-size-sm;
  font-weight: @font-weight-medium;
}

.parameter-presets__select {
  min-width: 220px;
  flex: 1 1 220px;
}

.parameter-presets__custom {
  display: flex;
  flex-wrap: wrap;
  gap: @spacing-xs;
  margin-top: @spacing-sm;
}

.parameter-presets__empty {
  margin: @spacing-xs 0 0;
  color: @text-tertiary;
  font-size: @font-size-xs;
}
</style>
