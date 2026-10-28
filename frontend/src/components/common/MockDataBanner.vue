<template>
  <a-alert
    v-if="mock"
    class="mock-data-banner"
    data-testid="mock-data-banner"
    type="warning"
    show-icon
    :message="resolvedDisclaimer"
  />
</template>

<script setup lang="ts">
  import { computed } from 'vue'

  /**
   * 演示模型（mock）数据横幅。
   *
   * 契约（其它页面会 import，接口要稳定）：
   * - props `mock?: boolean`：为真时渲染黄色告警条；为假时**不渲染任何 DOM**。
   * - props `disclaimer?: string`：自定义文案；留空使用默认文案。
   * - 根元素必须带 `data-testid="mock-data-banner"`。
   */
  const DEFAULT_DISCLAIMER =
    '本页数据由演示模型（mock）生成，仅用于界面与流程验证，不可用于科研决策'

  const props = withDefaults(
    defineProps<{
      mock?: boolean
      disclaimer?: string
    }>(),
    {
      mock: false,
      disclaimer: '',
    }
  )

  const resolvedDisclaimer = computed(() => props.disclaimer.trim() || DEFAULT_DISCLAIMER)
</script>

<style scoped lang="less">
  .mock-data-banner {
    margin-bottom: 16px;
  }
</style>
