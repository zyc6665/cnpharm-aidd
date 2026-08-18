<template>
  <aside class="external-database-panel" data-testid="external-database-panel">
    <header>
      <DatabaseOutlined />
      <span>外部数据库</span>
    </header>

    <div class="source-tabs" role="tablist" aria-label="外部数据库来源">
      <button
        v-for="source in sources"
        :key="source.id"
        type="button"
        :class="{ active: source.id === selectedSourceId }"
        @click="selectedSourceId = source.id"
      >
        {{ source.name }}
      </button>
    </div>

    <form @submit.prevent="submitImport">
      <label for="external-database-identifier">{{ identifierLabel }}</label>
      <input
        id="external-database-identifier"
        v-model.trim="identifier"
        data-testid="external-database-identifier"
        :placeholder="identifierPlaceholder"
        :disabled="disabled || loading || sources.length === 0"
      />
      <button
        data-testid="external-database-import"
        type="submit"
        :disabled="!canSubmit"
      >
        {{ loading ? '导入中...' : '导入到画布' }}
      </button>
    </form>

    <p>{{ helperText }}</p>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { DatabaseOutlined } from '@ant-design/icons-vue'
import type { ExternalDatabaseEntityType, ExternalDatabaseSource } from '@/api/external-databases'

const props = withDefaults(defineProps<{
  sources: ExternalDatabaseSource[]
  disabled?: boolean
  loading?: boolean
}>(), { disabled: false, loading: false })

const emit = defineEmits<{
  (event: 'import', value: {
    source: string
    entity_type: ExternalDatabaseEntityType
    identifier: string
  }): void
}>()

const selectedSourceId = ref('')
const identifier = ref('')

const selectedSource = computed(() =>
  props.sources.find(source => source.id === selectedSourceId.value) ?? props.sources[0]
)
const selectedEntityType = computed<ExternalDatabaseEntityType>(() =>
  selectedSource.value?.entity_types[0] ?? 'protein'
)
const identifierLabel = computed(() => selectedSource.value?.identifier_label ?? '编号')
const identifierPlaceholder = computed(() =>
  selectedEntityType.value === 'ligand' ? '例如 2244' : '例如 1ABC'
)
const helperText = computed(() => {
  if (!selectedSource.value) {
    return '暂无可用外部数据库来源。'
  }
  return selectedEntityType.value === 'ligand'
    ? '导入小分子后可在画布预览 2D/3D SDF。'
    : '导入蛋白后可在画布预览并下载 PDB。'
})
const canSubmit = computed(() =>
  Boolean(selectedSource.value && identifier.value.trim()) && !props.disabled && !props.loading
)

watch(
  () => props.sources,
  sources => {
    if (!sources.length) {
      selectedSourceId.value = ''
      return
    }
    const firstSource = sources[0]
    if (firstSource && !sources.some(source => source.id === selectedSourceId.value)) {
      selectedSourceId.value = firstSource.id
    }
  },
  { immediate: true }
)

function submitImport() {
  if (!canSubmit.value || !selectedSource.value) {
    return
  }
  emit('import', {
    source: selectedSource.value.id,
    entity_type: selectedEntityType.value,
    identifier: identifier.value.trim(),
  })
  identifier.value = ''
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.external-database-panel {
  width: 260px;
  padding: @spacing-sm;
  border-left: 1px solid @border-color;
  background: @bg-surface;
}

.external-database-panel header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: @spacing-sm;
  color: @text-primary;
  font-weight: 600;
}

.source-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: @spacing-sm;
}

.source-tabs button,
.external-database-panel form button {
  min-height: 32px;
  border: 1px solid @border-color;
  border-radius: @border-radius-sm;
  background: @bg-elevated;
  color: @text-secondary;
  cursor: pointer;
}

.source-tabs button.active {
  border-color: @accent-color;
  color: @accent-color;
}

.external-database-panel form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.external-database-panel label {
  color: @text-secondary;
  font-size: @font-size-xs;
}

.external-database-panel input {
  height: 32px;
  padding: 0 8px;
  border: 1px solid @border-color;
  border-radius: @border-radius-sm;
  background: @bg-elevated;
  color: @text-primary;
}

.external-database-panel form button {
  background: @accent-color;
  color: #fff;
}

.source-tabs button:disabled,
.external-database-panel input:disabled,
.external-database-panel form button:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.external-database-panel p {
  margin: @spacing-sm 0 0;
  color: @text-tertiary;
  font-size: @font-size-xs;
  line-height: 1.5;
}
</style>
