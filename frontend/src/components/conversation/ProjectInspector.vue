<template>
  <aside class="project-inspector" data-testid="project-inspector">
    <header><strong>项目上下文</strong><a-tag>{{ roleText }}</a-tag></header>
    <section><span>研究目标</span><p>{{ project?.goal || '尚未设置研究目标' }}</p></section>
    <section><span>模型策略</span><p>遵循项目策略</p></section>
    <section><span>数据边界</span><p>仅使用当前项目资源</p></section>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProjectResearchContext } from '@/types/conversations'

const props = defineProps<{ project: ProjectResearchContext | null }>()
const roleText = computed(() => ({ owner: '所有者', editor: '编辑者', runner: '运行者', viewer: '只读' })[props.project?.membership.role || 'viewer'])
</script>

<style scoped lang="less">
.project-inspector { min-width: 0; padding: 16px; border-left: 1px solid @border-color; background: @bg-surface; }
header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
section { padding: 13px 0; border-bottom: 1px solid @border-color-light; } section span { font-size: 12px; color: @text-tertiary; } section p { margin: 6px 0 0; color: @text-primary; line-height: 1.55; overflow-wrap: anywhere; }
</style>
