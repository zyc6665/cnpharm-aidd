<template>
  <div class="json-result-renderer" :class="{ 'json-result-renderer--nested': depth > 0 }">
    <div v-if="entries.length" class="json-result-list">
      <template v-for="entry in entries" :key="entry.key">
        <div
          v-if="entry.kind === 'scalar' || entry.kind === 'empty'"
          class="json-result-row"
        >
          <span class="json-result-label">{{ entry.label }}</span>
          <span class="json-result-value" :class="getValueClass(entry.rawValue)">
            {{ entry.value }}
          </span>
        </div>

        <section
          v-else-if="entry.kind === 'object'"
          class="json-result-section"
        >
          <div class="json-result-section__header">
            <h5>{{ entry.label }}</h5>
            <span>{{ t('tasks.jsonResultFields', { count: entry.children?.length || 0 }) }}</span>
          </div>
          <JsonResultRenderer
            :value="entry.rawValue"
            :entries="entry.children || []"
            :depth="depth + 1"
            :show-raw="false"
          />
        </section>

        <section
          v-else-if="entry.kind === 'array'"
          class="json-result-section"
        >
          <div class="json-result-section__header">
            <h5>{{ entry.label }}</h5>
            <span>{{ t('tasks.jsonResultItems', { count: entry.children?.length || 0 }) }}</span>
          </div>
          <div class="json-result-array">
            <div
              v-for="child in entry.children"
              :key="child.key"
              class="json-result-array__item"
            >
              <div class="json-result-array__index">{{ child.label }}</div>
              <JsonResultRenderer
                v-if="child.children?.length"
                :value="child.rawValue"
                :entries="child.children"
                :depth="depth + 1"
                :show-raw="false"
              />
              <span v-else class="json-result-value" :class="getValueClass(child.rawValue)">
                {{ child.value }}
              </span>
            </div>
          </div>
        </section>
      </template>
    </div>

    <details v-if="showRaw && rawJson" class="json-result-raw">
      <summary>{{ t('tasks.jsonResultRaw') }}</summary>
      <pre>{{ rawJson }}</pre>
    </details>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import {
    buildJsonResultEntries,
    type JsonResultEntry
  } from '@/domain/tasks'

  const props = withDefaults(defineProps<{
    value: unknown
    entries?: JsonResultEntry[]
    depth?: number
    showRaw?: boolean
  }>(), {
    entries: undefined,
    depth: 0,
    showRaw: true
  })

  const { t } = useI18n()
  const entries = computed(() => props.entries ?? buildJsonResultEntries(props.value))

  const rawJson = computed(() => {
    try {
      return JSON.stringify(props.value, null, 2)
    } catch {
      return ''
    }
  })

  function getValueClass(value: unknown) {
    if (typeof value === 'boolean') {
      return value ? 'json-result-value--true' : 'json-result-value--false'
    }

    if (typeof value === 'number') {
      return 'json-result-value--number'
    }

    if (value === null || value === undefined) {
      return 'json-result-value--empty'
    }

    return ''
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .json-result-renderer {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
  }

  .json-result-renderer--nested {
    gap: @spacing-sm;
  }

  .json-result-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .json-result-row {
    display: grid;
    grid-template-columns: minmax(120px, 0.36fr) minmax(0, 1fr);
    gap: @spacing-md;
    align-items: start;
    padding: @spacing-sm @spacing-md;
    border: 1px solid rgba(220, 227, 240, 0.92);
    border-radius: @border-radius-sm;
    background: @bg-elevated;
  }

  .json-result-label {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
  }

  .json-result-value {
    min-width: 0;
    color: @text-color-light-primary;
    line-height: 1.55;
    overflow-wrap: anywhere;
  }

  .json-result-value--number {
    color: #1d4ed8;
    font-variant-numeric: tabular-nums;
  }

  .json-result-value--true {
    color: @success-color;
    font-weight: @font-weight-semibold;
  }

  .json-result-value--false,
  .json-result-value--empty {
    color: @text-color-light-secondary;
  }

  .json-result-section {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
    padding: @spacing-md;
    border: 1px solid rgba(205, 214, 229, 0.95);
    border-radius: @border-radius-md;
    background: linear-gradient(180deg, @accent-color-light 0%, #f7faff 100%);
  }

  .json-result-section__header {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: baseline;
    padding-bottom: @spacing-xs;
    border-bottom: 1px solid rgba(220, 227, 240, 0.85);

    h5 {
      margin: 0;
      color: @text-color-light-primary;
      font-size: @font-size-md;
      font-weight: @font-weight-semibold;
    }

    span {
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
      white-space: nowrap;
    }
  }

  .json-result-array {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .json-result-array__item {
    display: grid;
    grid-template-columns: 72px minmax(0, 1fr);
    gap: @spacing-md;
    padding: @spacing-sm;
    border: 1px solid rgba(220, 227, 240, 0.9);
    border-radius: @border-radius-sm;
    background: @bg-elevated;
  }

  .json-result-array__index {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
  }

  .json-result-raw {
    border-top: 1px solid rgba(220, 227, 240, 0.9);
    padding-top: @spacing-sm;

    summary {
      cursor: pointer;
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
    }

    pre {
      margin: @spacing-sm 0 0;
      padding: @spacing-sm;
      border-radius: @border-radius-sm;
      background: #0f172a;
      color: #e2e8f0;
      overflow-x: auto;
      font-size: @font-size-sm;
    }
  }

  @media (max-width: @screen-sm) {
    .json-result-row,
    .json-result-array__item {
      grid-template-columns: 1fr;
      gap: @spacing-xs;
    }

    .json-result-section__header {
      flex-direction: column;
      gap: @spacing-xs;
    }
  }
</style>
