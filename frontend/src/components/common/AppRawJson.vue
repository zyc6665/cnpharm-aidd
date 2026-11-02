<template>
  <a-collapse ghost class="app-raw-json" :data-testid="testId">
    <a-collapse-panel key="raw" :header="title">
      <pre class="app-raw-json-body" :data-testid="testId ? `${testId}-body` : undefined">{{ pretty }}</pre>
    </a-collapse-panel>
  </a-collapse>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * 只读原始 JSON 折叠块。
 *
 * 之前全站有 12 处各写一遍 `<pre>{{ JSON.stringify(x, null, 2) }}</pre>`，
 * 样式、折叠行为、空值表现各不相同。凡是「给人看但默认折叠」的原始数据，
 * 一律用这个组件；编辑器里的可写文本框（ToolParameterForm 等）不走这里。
 */
const props = defineProps<{
  value: unknown
  title: string
  testId?: string
}>()

const pretty = computed(() => {
  try {
    return JSON.stringify(props.value ?? {}, null, 2)
  } catch {
    return String(props.value)
  }
})
</script>

<style scoped>
.app-raw-json-body {
  margin: 0;
  padding: 12px;
  max-height: 420px;
  overflow: auto;
  border: 1px solid var(--color-border, #d9d9d9);
  border-radius: 6px;
  background: var(--color-fill-quaternary, #fafafa);
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
