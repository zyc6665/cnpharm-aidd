<template>
  <section class="approval-card" aria-label="执行计划审批">
    <header><SafetyCertificateOutlined /><strong>执行前审批</strong><a-tag>{{ statusText }}</a-tag></header>
    <dl>
      <div><dt>工具</dt><dd>{{ plan.tool }}</dd></div>
      <div><dt>参数</dt><dd>{{ parameterText }}</dd></div>
      <div><dt>资源</dt><dd>{{ resourceText }}</dd></div>
      <div><dt>预计时间</dt><dd>{{ durationText }}</dd></div>
      <div><dt>联网风险</dt><dd>{{ plan.network_access ? '需要访问网络' : '不访问网络' }}</dd></div>
    </dl>
    <div v-if="plan.status === undefined || plan.status === 'pending'" class="approval-actions">
      <a-button :disabled="!canRun" @click="$emit('reject', plan.plan_id)">驳回</a-button>
      <a-button
        type="primary"
        :disabled="!canRun"
        data-testid="approve-plan"
        :title="canRun ? '批准执行' : '仅项目所有者或运行者可批准'"
        @click="$emit('approve', plan.plan_id)"
      >批准执行</a-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { SafetyCertificateOutlined } from '@ant-design/icons-vue'
import type { ApprovalContentBlock } from '@/types/conversations'

const props = defineProps<{ plan: ApprovalContentBlock; canRun: boolean }>()
defineEmits<{ approve: [planId: string]; reject: [planId: string] }>()

const parameterText = computed(() => Object.entries(props.plan.parameters).map(([key, value]) => `${key}: ${String(value)}`).join(' · ') || '无')
const resourceText = computed(() => Object.values(props.plan.resources).map(String).join(' · ') || '默认资源')
const durationText = computed(() => {
  const seconds = props.plan.estimated_duration_seconds
  if (!seconds) return '待评估'
  return seconds < 60 ? `约 ${seconds} 秒` : `约 ${Math.ceil(seconds / 60)} 分钟`
})
const statusText = computed(() => ({ approved: '已批准', rejected: '已驳回', pending: '待审批' })[props.plan.status || 'pending'])
</script>

<style scoped lang="less">
.approval-card { margin-top: 12px; border: 1px solid @border-color; border-left: 3px solid @warning-color; border-radius: 6px; background: @bg-surface; overflow: hidden; }
header { display: flex; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid @border-color; }
header :deep(.ant-tag) { margin-left: auto; }
dl { margin: 0; padding: 6px 14px; }
dl div { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 10px; padding: 7px 0; border-bottom: 1px solid @border-color-light; }
dl div:last-child { border: 0; }
dt { color: @text-tertiary; } dd { margin: 0; color: @text-primary; overflow-wrap: anywhere; }
.approval-actions { display: flex; justify-content: flex-end; gap: 8px; padding: 10px 14px; border-top: 1px solid @border-color; }
</style>
