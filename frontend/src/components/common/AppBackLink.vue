<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { readHistoryBack, resolveBackTarget } from '@/domain/navigation/back'

/**
 * 统一的页面返回入口，同时给出两个方向，让用户自己选：
 * 1. 「返回上一页」——浏览器历史里的来路（从哪里点进来就回哪里）；
 * 2. 父级链接——页面在信息架构里的上一层（直接打开 URL、或从历史里回不去时的可靠去处）。
 *
 * 只留一个都不够：只有父级会把从别处进来的用户拽走；只有「上一页」在直接打开链接时无处可去。
 */
const props = withDefaults(
  defineProps<{
    fallback: string
    /** 不传则用「返回上一页」；页面有自己的措辞时可以覆盖。 */
    label?: string
    /** 父级链接的文案，例如「返回靶点详情」。不传则不渲染父级链接。 */
    parentLabel?: string
    testId?: string
  }>(),
  { label: undefined, parentLabel: undefined, testId: undefined }
)

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const labelText = computed(() => props.label ?? t('common.backToPrevious'))
const parentTestId = computed(() => (props.testId ? `${props.testId}-parent` : 'back-parent'))

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
  <div class="app-back-links">
    <button type="button" class="app-back-link" :data-testid="testId" @click="handleBack">
      <span aria-hidden="true">←</span>
      {{ labelText }}
    </button>
    <template v-if="parentLabel">
      <span class="app-back-links__divider" aria-hidden="true">·</span>
      <router-link class="app-back-link app-back-link--parent" :to="fallback" :data-testid="parentTestId">
        {{ parentLabel }}
      </router-link>
    </template>
  </div>
</template>

<style scoped lang="less">
.app-back-links {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: @spacing-lg;
}

.app-back-links__divider {
  color: @text-tertiary;
  font-size: 12px;
}

.app-back-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: none;
  background: none;
  color: @text-tertiary;
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;

  &:hover {
    color: @primary-color;
  }
}
</style>
