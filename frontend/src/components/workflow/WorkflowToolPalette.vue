<template>
  <div class="workflow-sidebar-tool-library">
    <div class="sidebar-tool-library-header">
      <span class="rail-kicker">{{ t('workflow.palette.title') }}</span>
      <a-input-search
        :value="searchKeyword"
        :placeholder="t('workflow.palette.searchPlaceholder')"
        allow-clear
        @update:value="emit('update:searchKeyword', $event)"
      />
      <div class="sidebar-tool-filters">
        <a-select
          :value="stageFilter"
          size="small"
          allow-clear
          :placeholder="t('workflow.palette.filterStage')"
          :options="stageOptions"
          @change="emit('update:stageFilter', $event)"
        />
        <a-select
          :value="inputFilter"
          size="small"
          allow-clear
          :placeholder="t('workflow.palette.filterInput')"
          :options="inputOptions"
          @change="emit('update:inputFilter', $event)"
        />
        <a-select
          :value="outputFilter"
          size="small"
          allow-clear
          :placeholder="t('workflow.palette.filterOutput')"
          :options="outputOptions"
          @change="emit('update:outputFilter', $event)"
        />
        <a-select
          :value="executorFilter"
          size="small"
          allow-clear
          :placeholder="t('workflow.palette.filterExecutor')"
          :options="executorOptions"
          @change="emit('update:executorFilter', $event)"
        />
      </div>
    </div>
    <div class="sidebar-tool-list">
      <section v-for="group in toolGroups" :key="group.key" class="sidebar-tool-group">
        <div class="sidebar-tool-group-title">{{ group.label }}</div>
        <button
          v-for="tool in group.tools"
          :key="tool.slug"
          type="button"
          class="sidebar-tool-item"
          draggable="true"
          @click="emit('add-tool', tool.slug)"
          @dragstart="handleToolDragStart($event, tool.slug)"
        >
          <span class="sidebar-tool-name">{{ tool.name || tool.slug }}</span>
          <span v-if="tool.description" class="sidebar-tool-desc">{{ tool.description }}</span>
          <span class="sidebar-tool-meta">
            <span v-if="tool.executorType">{{ tool.executorType }}</span>
            <span v-if="resourceProfileLabel(tool.resourceProfile)">
              {{ resourceProfileLabel(tool.resourceProfile) }}
            </span>
          </span>
          <span class="sidebar-tool-action">{{ t('workflow.palette.addNode') }}</span>
        </button>
      </section>
      <a-empty
        v-if="tools.length === 0"
        class="sidebar-tool-empty"
        :description="t('workflow.palette.empty')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

interface PaletteTool {
  slug: string
  name: string
  description?: string
  capability?: string
  stage?: string
  executorType?: string
  resourceProfile?: Record<string, unknown>
}

const props = defineProps<{
  searchKeyword: string
  stageFilter?: string
  inputFilter?: string
  outputFilter?: string
  executorFilter?: string
  stageOptions: Array<{ value: string; label: string }>
  inputOptions: Array<{ value: string; label: string }>
  outputOptions: Array<{ value: string; label: string }>
  executorOptions: Array<{ value: string; label: string }>
  tools: PaletteTool[]
}>()

const emit = defineEmits<{
  'update:searchKeyword': [value: string]
  'update:stageFilter': [value: string | undefined]
  'update:inputFilter': [value: string | undefined]
  'update:outputFilter': [value: string | undefined]
  'update:executorFilter': [value: string | undefined]
  'add-tool': [toolSlug: string]
}>()

const { t } = useI18n()

const toolGroups = computed(() => {
  const groups = new Map<string, PaletteTool[]>()
  for (const tool of props.tools) {
    const key = tool.capability || tool.stage || 'other_tools'
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key)!.push(tool)
  }
  return Array.from(groups.entries()).map(([key, tools]) => ({
    key,
    label: key,
    tools,
  }))
})

function resourceProfileLabel(resourceProfile?: Record<string, unknown>): string {
  if (!resourceProfile) {
    return ''
  }
  const segments = [String(resourceProfile.tier || '')].filter(Boolean)
  if (hasResourceValue(resourceProfile.cpu)) {
    segments.push(`CPU ${resourceProfile.cpu}`)
  }
  if (hasResourceValue(resourceProfile.memory_gb)) {
    segments.push(`MEM ${resourceProfile.memory_gb}GB`)
  }
  if (resourceProfile.gpu_required) {
    segments.push(
      hasResourceValue(resourceProfile.gpu_memory_gb)
        ? `GPU ${resourceProfile.gpu_memory_gb}GB`
        : 'GPU'
    )
  }
  return segments.join(' · ')
}

function hasResourceValue(value: unknown): boolean {
  return value !== undefined && value !== null && value !== ''
}

function handleToolDragStart(event: DragEvent, toolSlug: string) {
  if (!event.dataTransfer) {
    return
  }

  event.dataTransfer.effectAllowed = 'copy'
  event.dataTransfer.setData('application/x-workflow-tool', toolSlug)
  event.dataTransfer.setData('text/plain', toolSlug)
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workflow-sidebar-tool-library {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-top: 1px solid @border-color-light;
}

.rail-kicker {
  display: block;
  margin-bottom: @spacing-xs;
  color: @text-color-light-tertiary;
  font-size: @font-size-xs;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.sidebar-tool-library-header {
  display: grid;
  gap: @spacing-xs;
  padding: @spacing-sm;
}

.sidebar-tool-filters {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: @spacing-xs;
}

.sidebar-tool-list {
  display: grid;
  gap: @spacing-xs;
  padding: 0 @spacing-sm @spacing-sm;
  overflow: auto;
}

.sidebar-tool-group {
  display: grid;
  gap: @spacing-xs;
}

.sidebar-tool-group + .sidebar-tool-group {
  margin-top: @spacing-sm;
}

.sidebar-tool-group-title {
  color: @text-color-light-tertiary;
  font-size: @font-size-xs;
  font-weight: 800;
  line-height: 1.2;
}

.sidebar-tool-item {
  min-width: 0;
  display: grid;
  gap: 3px;
  padding: @spacing-sm;
  border: 1px solid @border-color-hover;
  border-radius: @border-radius-sm;
  background: @bg-elevated;
  text-align: left;
  cursor: pointer;
}

.sidebar-tool-item:hover,
.sidebar-tool-item:focus-visible {
  border-color: rgba(59, 130, 246, 0.3);
  background: @primary-color-light;
  outline: none;
}

.sidebar-tool-name {
  color: @text-color-light-primary;
  font-size: @font-size-sm;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-tool-desc {
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.sidebar-tool-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  color: @text-color-light-tertiary;
  font-size: @font-size-xs;
}

.sidebar-tool-meta span {
  max-width: 100%;
  padding: 1px 5px;
  border-radius: @border-radius-sm;
  background: @bg-hover;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-tool-action {
  color: @primary-color;
  font-size: @font-size-xs;
  font-weight: 700;
}

.sidebar-tool-empty {
  padding: @spacing-sm 0;
}
</style>
