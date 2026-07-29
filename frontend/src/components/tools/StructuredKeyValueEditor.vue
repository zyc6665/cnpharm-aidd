<template>
  <div class="structured-key-value-editor">
    <div class="structured-editor-toolbar">
      <span class="structured-editor-count">{{ modelValue.length }} 项</span>
      <a-button size="small" type="dashed" @click="addEntry">
        <PlusOutlined />
        {{ addLabel }}
      </a-button>
    </div>

    <p v-if="modelValue.length === 0" class="structured-editor-empty">{{ emptyText }}</p>
    <div
      v-for="(entry, index) in modelValue"
      :key="index"
      class="structured-key-value-row"
    >
      <a-input
        :value="entry.key"
        :placeholder="keyPlaceholder"
        @update:value="updateEntry(index, 'key', $event)"
      />
      <a-input
        :value="entry.value"
        :placeholder="valuePlaceholder"
        @update:value="updateEntry(index, 'value', $event)"
      />
      <a-tooltip title="删除此项">
        <a-button
          type="text"
          danger
          :aria-label="`删除第 ${index + 1} 项`"
          @click="removeEntry(index)"
        >
          <DeleteOutlined />
        </a-button>
      </a-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import type { KeyValueEntry } from '@/utils/tool-config-editors'

const props = withDefaults(
  defineProps<{
    modelValue: KeyValueEntry[]
    addLabel?: string
    emptyText?: string
    keyPlaceholder?: string
    valuePlaceholder?: string
  }>(),
  {
    addLabel: '添加配置项',
    emptyText: '暂无配置项',
    keyPlaceholder: '键',
    valuePlaceholder: '值'
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: KeyValueEntry[]]
}>()

function addEntry() {
  emit('update:modelValue', [...props.modelValue, { key: '', value: '' }])
}

function updateEntry(index: number, field: keyof KeyValueEntry, value: string) {
  emit(
    'update:modelValue',
    props.modelValue.map((entry, entryIndex) =>
      entryIndex === index ? { ...entry, [field]: value } : entry
    )
  )
}

function removeEntry(index: number) {
  emit('update:modelValue', props.modelValue.filter((_, entryIndex) => entryIndex !== index))
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.structured-key-value-editor {
  display: grid;
  gap: @spacing-sm;
}

.structured-editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-sm;
}

.structured-editor-count,
.structured-editor-empty {
  color: @text-secondary;
  font-size: @font-size-sm;
}

.structured-editor-empty {
  margin: 0;
  padding: @spacing-sm 0;
}

.structured-key-value-row {
  display: grid;
  grid-template-columns: minmax(120px, 0.45fr) minmax(180px, 1fr) 32px;
  gap: @spacing-sm;
  align-items: center;
}

@media (max-width: @screen-sm) {
  .structured-key-value-row {
    grid-template-columns: minmax(0, 1fr) 32px;
  }

  .structured-key-value-row :deep(.ant-input:first-child) {
    grid-column: 1 / -1;
  }
}
</style>
