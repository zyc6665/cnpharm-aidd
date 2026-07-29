<template>
  <div class="structured-string-list-editor">
    <div class="structured-editor-toolbar">
      <span class="structured-editor-count">{{ modelValue.length }} 项</span>
      <a-button size="small" type="dashed" @click="addItem">
        <PlusOutlined />
        {{ addLabel }}
      </a-button>
    </div>

    <p v-if="modelValue.length === 0" class="structured-editor-empty">{{ emptyText }}</p>
    <div
      v-for="(item, index) in modelValue"
      :key="index"
      class="structured-string-list-row"
    >
      <span class="structured-item-index">{{ index + 1 }}</span>
      <a-input
        :value="item"
        :placeholder="placeholder"
        @update:value="updateItem(index, $event)"
      />
      <a-tooltip title="删除此项">
        <a-button
          type="text"
          danger
          :aria-label="`删除第 ${index + 1} 项`"
          @click="removeItem(index)"
        >
          <DeleteOutlined />
        </a-button>
      </a-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'

const props = withDefaults(
  defineProps<{
    modelValue: string[]
    addLabel?: string
    emptyText?: string
    placeholder?: string
  }>(),
  {
    addLabel: '添加一项',
    emptyText: '暂无配置项',
    placeholder: '输入完整值'
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

function addItem() {
  emit('update:modelValue', [...props.modelValue, ''])
}

function updateItem(index: number, value: string) {
  emit(
    'update:modelValue',
    props.modelValue.map((item, itemIndex) => (itemIndex === index ? value : item))
  )
}

function removeItem(index: number) {
  emit('update:modelValue', props.modelValue.filter((_, itemIndex) => itemIndex !== index))
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.structured-string-list-editor {
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

.structured-string-list-row {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 32px;
  gap: @spacing-sm;
  align-items: center;
}

.structured-item-index {
  color: @text-secondary;
  font-family: @font-family-mono;
  font-size: @font-size-xs;
  text-align: center;
}

@media (max-width: @screen-sm) {
  .structured-string-list-row {
    grid-template-columns: 24px minmax(0, 1fr) 32px;
    gap: @spacing-xs;
  }
}
</style>
