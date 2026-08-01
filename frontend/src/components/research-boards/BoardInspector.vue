<template>
  <aside class="board-inspector" data-testid="board-inspector" aria-label="白板检查器">
    <header>检查器</header>
    <label>
      <span>名称</span>
      <a-input :value="name" :maxlength="160" @update:value="emit('update:name', String($event))" />
    </label>
    <label>
      <span>说明</span>
      <a-textarea :value="description" :rows="3" :maxlength="2000" @update:value="emit('update:description', String($event))" />
    </label>
    <section class="selection">
      <span>当前选中</span>
      <template v-if="selectedNode">
        <strong>{{ nodeTypeLabel }}</strong>
        <small>{{ selectedNode.id }}</small>
        <a-button danger size="small" @click="emit('remove-selected')">删除对象</a-button>
      </template>
      <small v-else>未选择</small>
    </section>
    <footer :class="`is-${saveState}`">{{ saveStateLabel }}</footer>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BoardNode } from './ResearchBoardCanvas.vue'

const props = defineProps<{
  name: string
  description: string
  selectedNode: BoardNode | null
  saveState: 'saved' | 'dirty' | 'saving' | 'error'
}>()
const emit = defineEmits<{
  (event: 'update:name', value: string): void
  (event: 'update:description', value: string): void
  (event: 'remove-selected'): void
}>()
const nodeTypeLabel = computed(() => props.selectedNode
  ? ({ note: '研究便笺', file: '文件', image: '图片', artifact: '科研产物', tool: '工具' })[props.selectedNode.type]
  : '')
const saveStateLabel = computed(() => ({
  saved: '已保存', dirty: '有未保存修改', saving: '正在保存', error: '保存失败',
})[props.saveState])
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';
.board-inspector { width: 260px; padding: @spacing-md; border-left: 1px solid @border-color; background: @bg-surface; overflow-y: auto; }
.board-inspector header { margin-bottom: @spacing-md; font-weight: @font-weight-semibold; }
.board-inspector label { display: block; margin-bottom: @spacing-md; }
.board-inspector label > span, .selection > span { display: block; margin-bottom: 6px; color: @text-tertiary; font-size: @font-size-xs; }
.selection { display: grid; gap: 6px; padding-top: @spacing-md; border-top: 1px solid @border-color; }
.selection small { color: @text-tertiary; overflow-wrap: anywhere; }
.board-inspector footer { margin-top: @spacing-lg; color: @text-tertiary; font-size: @font-size-xs; }
.board-inspector footer.is-error { color: @error-color; }
.board-inspector footer.is-dirty { color: @warning-color; }
</style>
