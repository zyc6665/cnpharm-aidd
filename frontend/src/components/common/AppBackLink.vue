<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { readHistoryBack, resolveBackTarget } from '@/domain/navigation/back'

/**
 * 统一的「返回」入口：优先回浏览器历史里的上一页，回不去才走 `fallback`。
 * 详情页的父级链接仍然要传——它是「直接打开这个 URL」时唯一可靠的方向。
 */
const props = withDefaults(
  defineProps<{
    fallback: string
    /** 不传则用「返回上一页」；页面有自己的措辞时（例如「返回口袋」）可以覆盖。 */
    label?: string
    testId?: string
  }>(),
  { label: undefined, testId: undefined }
)

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const labelText = computed(() => props.label ?? t('common.backToPrevious'))

function handleBack(): void {
  const decision = resolveBackTarget({
    historyBack: readHistoryBack(window.history.state),
    currentPath: route.fullPath,
    fallback: props.fallback
  })
  if (decision.mode === 'back') {
    router.back()
    return
  }
  void router.push(decision.to)
}
</script>

<template>
  <button type="button" class="app-back-link" :data-testid="testId" @click="handleBack">
    <span aria-hidden="true">←</span>
    {{ labelText }}
  </button>
</template>

<style scoped lang="less">
.app-back-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-bottom: @spacing-lg;
  padding: 0;
  border: none;
  background: none;
  color: @text-tertiary;
  font-size: 13px;
  cursor: pointer;

  &:hover {
    color: @primary-color;
  }
}
</style>
