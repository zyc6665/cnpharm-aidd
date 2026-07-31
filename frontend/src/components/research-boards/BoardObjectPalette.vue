<template>
  <aside class="object-palette" data-testid="board-object-palette" aria-label="白板对象">
    <header>对象</header>
    <button v-for="item in items" :key="item.type" type="button" :disabled="item.disabled" @click="emit('add', item.type)">
      <component :is="item.icon" />
      <span>{{ item.label }}</span>
    </button>
  </aside>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import {
  DatabaseOutlined,
  ExperimentOutlined,
  FileImageOutlined,
  FileOutlined,
  FileTextOutlined,
} from '@ant-design/icons-vue'
import type { BoardNodeType } from './ResearchBoardCanvas.vue'

const props = defineProps<{ hasFiles: boolean; hasImages: boolean; hasTools: boolean; hasArtifacts: boolean }>()
const emit = defineEmits<{ (event: 'add', type: BoardNodeType): void }>()

interface PaletteItem { type: BoardNodeType; label: string; icon: Component; disabled: boolean }
const items = computed<PaletteItem[]>(() => [
  { type: 'note', label: '便笺', icon: FileTextOutlined, disabled: false },
  { type: 'file', label: '文件', icon: FileOutlined, disabled: !props.hasFiles },
  { type: 'image', label: '图片', icon: FileImageOutlined, disabled: !props.hasImages },
  { type: 'artifact', label: '科研产物', icon: DatabaseOutlined, disabled: !props.hasArtifacts },
  { type: 'tool', label: '工具', icon: ExperimentOutlined, disabled: !props.hasTools },
])
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';
.object-palette { width: 76px; padding: @spacing-sm 6px; border-right: 1px solid @border-color; background: @bg-surface; }
.object-palette header { margin-bottom: @spacing-sm; color: @text-tertiary; font-size: @font-size-xs; text-align: center; }
.object-palette button { width: 100%; min-height: 54px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; border: 0; background: transparent; color: @text-secondary; font-size: @font-size-xs; cursor: pointer; }
.object-palette button:hover:not(:disabled) { background: @bg-hover; color: @text-primary; }
.object-palette button:disabled { opacity: .4; cursor: not-allowed; }
.object-palette button :deep(svg) { font-size: 18px; }
</style>
