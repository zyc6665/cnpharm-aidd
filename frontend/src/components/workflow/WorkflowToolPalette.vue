<template>
  <div class="workflow-sidebar-tool-library">
    <div class="sidebar-tool-library-header">
      <div class="sidebar-tool-library-title">
        <span class="rail-kicker">{{ t('workflow.palette.title') }}</span>
        <span class="sidebar-tool-summary">
          {{ t('workflow.palette.toolsAvailable', { count: displayedTools.length }) }}
        </span>
      </div>
      <a-input-search
        class="sidebar-tool-search"
        :value="searchKeyword"
        :placeholder="t('workflow.palette.searchPlaceholder')"
        allow-clear
        @update:value="emit('update:searchKeyword', $event)"
      />
      <div class="sidebar-tool-quick-filter-panel">
        <div class="sidebar-tool-filter-heading">
          <span>{{ t('workflow.palette.quickFilterTitle') }}</span>
          <button
            type="button"
            class="sidebar-tool-advanced-toggle"
            :aria-expanded="showAdvancedFilters"
            @click="showAdvancedFilters = !showAdvancedFilters"
          >
            {{
              showAdvancedFilters
                ? t('workflow.palette.hideAdvanced')
                : t('workflow.palette.showAdvanced')
            }}
          </button>
        </div>
        <div class="sidebar-tool-quick-filters">
          <button
            v-for="filter in quickFilterOptions"
            :key="filter.key"
            type="button"
            class="sidebar-tool-quick-filter"
            :class="{ 'is-active': selectedQuickFilter === filter.key }"
            @click="selectedQuickFilter = filter.key"
          >
            <span>{{ filter.label }}</span>
            <strong>{{ filter.count }}</strong>
          </button>
        </div>
      </div>
      <div v-if="showAdvancedFilters" class="sidebar-tool-filter-card">
        <span class="sidebar-tool-filter-label">{{ t('workflow.palette.filterTitle') }}</span>
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
    </div>
    <div class="sidebar-tool-list">
      <section v-for="group in toolGroups" :key="group.key" class="sidebar-tool-group">
        <div class="sidebar-tool-group-header">
          <div class="sidebar-tool-group-copy">
            <span class="sidebar-tool-group-title">{{ group.label }}</span>
            <span class="sidebar-tool-group-key">{{ group.key }}</span>
          </div>
          <span class="sidebar-tool-group-count">{{ group.tools.length }}</span>
        </div>
        <div class="sidebar-tool-grid">
          <button
            v-for="tool in group.tools"
            :key="tool.slug"
            type="button"
            class="sidebar-tool-item"
            draggable="true"
            @click="emit('add-tool', tool.slug)"
            @dragstart="handleToolDragStart($event, tool.slug)"
          >
            <span class="sidebar-tool-card-head">
              <span class="sidebar-tool-name">{{ tool.name || tool.slug }}</span>
              <span v-if="tool.executorType" class="sidebar-tool-executor">{{ tool.executorType }}</span>
            </span>
            <span v-if="tool.description" class="sidebar-tool-desc">{{ tool.description }}</span>
            <span class="sidebar-tool-meta">
              <span v-if="resourceProfileLabel(tool.resourceProfile)">
                {{ resourceProfileLabel(tool.resourceProfile) }}
              </span>
              <span>{{ tool.slug }}</span>
            </span>
            <span class="sidebar-tool-action">{{ t('workflow.palette.dragOrClick') }}</span>
          </button>
        </div>
      </section>
      <a-empty
        v-if="displayedTools.length === 0"
        class="sidebar-tool-empty"
        :description="t('workflow.palette.empty')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

interface PaletteTool {
  slug: string
  name: string
  description?: string
  category_id?: string
  category?: string
  tags?: PaletteToolTag[]
  capability?: string
  stage?: string
  executorType?: string
  resourceProfile?: Record<string, unknown>
}

interface PaletteToolTag {
  id?: string
  name: string
  color?: string
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

const { t, te } = useI18n()

type QuickFilterKind = 'all' | 'category' | 'tag'

interface QuickFilterOption {
  key: string
  kind: QuickFilterKind
  id?: string
  label: string
  count: number
}

const showAdvancedFilters = ref(false)
const selectedQuickFilter = ref('all')

const GROUP_ORDER = [
  'external_database_fetch',
  'protein_preparation',
  'ligand_preparation',
  'ligand_format_conversion',
  'conformer_generation',
  'property_prediction',
  'admet_prediction',
  'toxicity_prediction',
  'synthetic_accessibility',
  'molecular_docking',
  'docking_rescore',
  'molecular_dynamics',
  'interaction_analysis',
  'other_tools',
]

const displayedTools = computed(() => {
  return props.tools.filter(tool => matchesQuickFilter(tool, selectedQuickFilter.value))
})

const quickFilterOptions = computed(() => {
  const filters: QuickFilterOption[] = [
    {
      key: 'all',
      kind: 'all',
      label: t('workflow.palette.quickFilters.all'),
      count: props.tools.length,
    },
  ]
  filters.push(...buildCategoryFilters(props.tools))
  filters.push(...buildTagFilters(props.tools))
  return filters
})

const toolGroups = computed(() => {
  const groups = new Map<string, PaletteTool[]>()
  for (const tool of displayedTools.value) {
    const key = groupKeyForTool(tool)
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key)!.push(tool)
  }
  return Array.from(groups.entries())
    .sort(compareToolGroups)
    .map(([key, tools]) => ({
      key,
      label: formatGroupLabel(key),
      tools: [...tools].sort((first, second) =>
        displayToolName(first).localeCompare(displayToolName(second))
      ),
    }))
})

function compareToolGroups(
  [firstKey]: [string, PaletteTool[]],
  [secondKey]: [string, PaletteTool[]]
): number {
  const firstIndex = GROUP_ORDER.indexOf(firstKey)
  const secondIndex = GROUP_ORDER.indexOf(secondKey)
  const normalizedFirstIndex = firstIndex === -1 ? GROUP_ORDER.length : firstIndex
  const normalizedSecondIndex = secondIndex === -1 ? GROUP_ORDER.length : secondIndex
  if (normalizedFirstIndex !== normalizedSecondIndex) {
    return normalizedFirstIndex - normalizedSecondIndex
  }
  return formatGroupLabel(firstKey).localeCompare(formatGroupLabel(secondKey))
}

function formatGroupLabel(key: string): string {
  if (key.startsWith('category:')) {
    return key.slice('category:'.length)
  }
  const labelKey = `workflow.palette.categories.${key}`
  return te(labelKey) ? t(labelKey) : humanizeKey(key)
}

function humanizeKey(key: string): string {
  return key
    .split(/[_-]+/)
    .filter(Boolean)
    .map(segment => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ')
}

function displayToolName(tool: PaletteTool): string {
  return tool.name || tool.slug
}

function buildCategoryFilters(tools: PaletteTool[]): QuickFilterOption[] {
  const filters = new Map<string, QuickFilterOption>()
  for (const tool of tools) {
    const categoryLabel = normalizedText(tool.category)
    if (!categoryLabel) {
      continue
    }
    const categoryId = normalizedText(tool.category_id) || categoryLabel
    const key = `category:${categoryId}`
    const existing = filters.get(key)
    if (existing) {
      existing.count += 1
    } else {
      filters.set(key, {
        key,
        kind: 'category',
        id: categoryId,
        label: categoryLabel,
        count: 1,
      })
    }
  }
  return [...filters.values()].sort(compareQuickFilters)
}

function buildTagFilters(tools: PaletteTool[]): QuickFilterOption[] {
  const filters = new Map<string, QuickFilterOption>()
  for (const tool of tools) {
    for (const tag of tool.tags ?? []) {
      const tagLabel = normalizedText(tag.name)
      if (!tagLabel) {
        continue
      }
      const tagId = normalizedText(tag.id) || tagLabel
      const key = `tag:${tagId}`
      const existing = filters.get(key)
      if (existing) {
        existing.count += 1
      } else {
        filters.set(key, {
          key,
          kind: 'tag',
          id: tagId,
          label: tagLabel,
          count: 1,
        })
      }
    }
  }
  return [...filters.values()].sort(compareQuickFilters)
}

function compareQuickFilters(first: QuickFilterOption, second: QuickFilterOption): number {
  if (first.count !== second.count) {
    return second.count - first.count
  }
  return first.label.localeCompare(second.label)
}

function matchesQuickFilter(tool: PaletteTool, filterKey: string): boolean {
  if (filterKey === 'all') {
    return true
  }
  const [kind, id] = filterKey.split(':', 2)
  if (!id) {
    return true
  }
  if (kind === 'category') {
    return [tool.category_id, tool.category]
      .map(value => normalizedText(value))
      .includes(id)
  }
  if (kind === 'tag') {
    return (tool.tags ?? []).some(tag => {
      return [tag.id, tag.name].map(value => normalizedText(value)).includes(id)
    })
  }
  return true
}

function groupKeyForTool(tool: PaletteTool): string {
  const category = normalizedText(tool.category)
  if (category) {
    return `category:${category}`
  }
  return tool.capability || tool.stage || 'other_tools'
}

function normalizedText(value?: string): string {
  return (value ?? '').trim()
}

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
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.035), transparent 180px);
}

.rail-kicker {
  display: block;
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
  border-bottom: 1px solid @border-color-light;
}

.sidebar-tool-library-title {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-xs;
}

.sidebar-tool-summary {
  flex: 0 0 auto;
  padding: 2px 7px;
  border: 1px solid @accent-color-border;
  border-radius: @border-radius-sm;
  background: @accent-color-light;
  color: @primary-color;
  font-size: @font-size-xs;
  font-weight: 800;
}

.sidebar-tool-search {
  :deep(.ant-input-affix-wrapper) {
    border-color: @border-color-hover;
    background: @bg-elevated;
  }
}

.sidebar-tool-filter-card {
  display: grid;
  gap: @spacing-xs;
  padding: @spacing-xs;
  border: 1px solid @border-color-light;
  border-radius: @border-radius-md;
  background: @bg-elevated;
}

.sidebar-tool-quick-filter-panel {
  display: grid;
  gap: @spacing-xs;
  padding: @spacing-xs;
  border: 1px solid @accent-color-border;
  border-radius: @border-radius-md;
  background:
    linear-gradient(180deg, rgba(59, 130, 246, 0.06), rgba(34, 197, 94, 0.025)),
    @bg-elevated;
}

.sidebar-tool-filter-heading {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-xs;
  color: @text-color-light-tertiary;
  font-size: @font-size-xs;
  font-weight: 800;
}

.sidebar-tool-advanced-toggle {
  flex: 0 0 auto;
  padding: 0;
  border: 0;
  background: transparent;
  color: @primary-color;
  font-size: @font-size-xs;
  font-weight: 800;
  cursor: pointer;
}

.sidebar-tool-advanced-toggle:hover,
.sidebar-tool-advanced-toggle:focus-visible {
  color: @accent-color-hover;
  outline: none;
}

.sidebar-tool-quick-filters {
  display: flex;
  flex-wrap: wrap;
  gap: @spacing-xs;
}

.sidebar-tool-quick-filter {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  padding: 5px 7px;
  border: 1px solid @border-color-light;
  border-radius: 999px;
  background: @bg-elevated;
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
  font-weight: 800;
  line-height: 1.2;
  cursor: pointer;
  transition: border-color @transition-fast, background @transition-fast, color @transition-fast;
}

.sidebar-tool-quick-filter span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-tool-quick-filter strong {
  min-width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
  border-radius: 999px;
  background: @bg-hover;
  color: @text-color-light-tertiary;
  font-size: 10px;
}

.sidebar-tool-quick-filter:hover,
.sidebar-tool-quick-filter:focus-visible,
.sidebar-tool-quick-filter.is-active {
  border-color: rgba(59, 130, 246, 0.42);
  background: @primary-color-light;
  color: @primary-color;
  outline: none;
}

.sidebar-tool-quick-filter.is-active strong {
  background: rgba(59, 130, 246, 0.18);
  color: @primary-color;
}

.sidebar-tool-filter-label {
  color: @text-color-light-tertiary;
  font-size: @font-size-xs;
  font-weight: 800;
}

.sidebar-tool-filters {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: @spacing-xs;

  :deep(.ant-select-selector) {
    border-color: @border-color-light !important;
    background: @bg-elevated !important;
  }
}

.sidebar-tool-list {
  display: grid;
  gap: @spacing-sm;
  padding: @spacing-sm;
  overflow: auto;
}

.sidebar-tool-group {
  display: grid;
  gap: @spacing-xs;
  padding: @spacing-xs;
  border: 1px solid @border-color-light;
  border-radius: @border-radius-md;
  background: @bg-surface;
}

.sidebar-tool-group + .sidebar-tool-group {
  margin-top: 0;
}

.sidebar-tool-group-header {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-xs;
  padding: 2px 2px @spacing-xs;
  border-bottom: 1px solid @border-color-light;
}

.sidebar-tool-group-copy {
  min-width: 0;
  display: grid;
  gap: 1px;
}

.sidebar-tool-group-title {
  color: @text-color-light-tertiary;
  font-size: @font-size-xs;
  font-weight: 800;
  line-height: 1.2;
}

.sidebar-tool-group-key {
  color: @text-color-light-disabled;
  font-family: @font-family-mono;
  font-size: 10px;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-tool-group-count {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: @border-radius-round;
  background: @bg-elevated;
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
  font-weight: 800;
}

.sidebar-tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
  gap: @spacing-xs;
}

.sidebar-tool-item {
  min-width: 0;
  display: grid;
  grid-template-rows: auto minmax(34px, auto) auto auto;
  gap: 5px;
  padding: @spacing-sm;
  border: 1px solid @border-color-hover;
  border-radius: @border-radius-sm;
  background:
    linear-gradient(180deg, @bg-surface, @bg-elevated),
    @bg-elevated;
  text-align: left;
  cursor: pointer;
  transition: border-color @transition-fast, background @transition-fast, box-shadow @transition-fast, transform @transition-fast;
}

.sidebar-tool-item:hover,
.sidebar-tool-item:focus-visible {
  border-color: rgba(59, 130, 246, 0.42);
  background:
    linear-gradient(180deg, rgba(59, 130, 246, 0.13), rgba(34, 197, 94, 0.04)),
    @bg-elevated;
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.16);
  transform: translateY(-1px);
  outline: none;
}

.sidebar-tool-card-head {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: @spacing-xs;
}

.sidebar-tool-name {
  min-width: 0;
  color: @text-color-light-primary;
  font-size: @font-size-sm;
  font-weight: 800;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.sidebar-tool-executor {
  flex: 0 0 auto;
  max-width: 74px;
  padding: 1px 5px;
  border-radius: @border-radius-sm;
  background: rgba(34, 197, 94, 0.12);
  color: @success-color;
  font-size: 10px;
  font-weight: 800;
  line-height: 1.4;
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
  padding: 2px 6px;
  border-radius: @border-radius-sm;
  background: @bg-hover;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-tool-action {
  justify-self: start;
  padding-top: 2px;
  border-top: 1px solid @border-color-light;
  color: @primary-color;
  font-size: @font-size-xs;
  font-weight: 700;
}

.sidebar-tool-empty {
  padding: @spacing-sm 0;
}

@media (max-width: @screen-sm) {
  .sidebar-tool-filters,
  .sidebar-tool-grid {
    grid-template-columns: 1fr;
  }
}
</style>
