<template>
  <section class="trace">
    <button class="trace-toggle" type="button" @click="expanded = !expanded">
      <RightOutlined :class="{ expanded }" />
      <span>智能体过程</span>
      <span class="count">{{ events.length }}</span>
    </button>
    <ol v-if="expanded">
      <li v-for="event in events" :key="event.sequence" :class="{ failed: event.event_type.includes('fail') }">
        <span class="sequence">{{ event.sequence }}</span>
        <span>{{ eventLabel(event) }}</span>
      </li>
    </ol>
    <div v-if="hasFailure" class="failure-state">
      <WarningOutlined />失败后可重试
      <a-button size="small" data-testid="retry-run" @click="$emit('retry')">重试</a-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { RightOutlined, WarningOutlined } from '@ant-design/icons-vue'
import type { AgentEvent } from '@/types/conversations'

const props = defineProps<{ events: AgentEvent[]; showRetry?: boolean }>()
defineEmits<{ retry: [] }>()
const expanded = ref(false)
const hasFailure = computed(() => props.showRetry || props.events.some(event => event.event_type.includes('fail')))
const eventLabel = (event: AgentEvent) => String(event.payload.message || event.payload.summary || event.event_type.replace(/_/g, ' '))
</script>

<style scoped lang="less">
.trace { width: min(780px, 100%); margin: 0 auto; padding: 0 28px; }
.trace-toggle { display: flex; align-items: center; gap: 7px; height: 34px; padding: 0; border: 0; background: transparent; color: @text-secondary; cursor: pointer; }
.trace-toggle svg { transition: transform .15s; }.trace-toggle svg.expanded { transform: rotate(90deg); }.count { color: @text-tertiary; }
ol { max-height: 180px; margin: 0 0 10px; padding: 4px 0; list-style: none; overflow: auto; }
li { display: grid; grid-template-columns: 28px 1fr; padding: 5px 8px; font-size: 12px; color: @text-secondary; } li.failed { color: @error-color; }.sequence { color: @text-tertiary; }
.failure-state { display: flex; align-items: center; gap: 8px; padding: 9px 10px; border-left: 3px solid @error-color; background: @error-color-light; color: @error-color; }
.failure-state :deep(.ant-btn) { margin-left: auto; }
</style>
