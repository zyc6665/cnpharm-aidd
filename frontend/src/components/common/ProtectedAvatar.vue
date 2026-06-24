<template>
  <a-avatar :size="size" :src="displaySrc">
    <template v-if="$slots.icon" #icon>
      <slot name="icon" />
    </template>
    <slot />
  </a-avatar>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import {
  createProtectedObjectUrl,
  isProtectedFileDownloadUrl
} from '@/utils/protected-file-access'

const props = defineProps<{
  src?: string
  size?: number
}>()

const displaySrc = ref<string | undefined>(props.src)
let revokeCurrentObjectUrl: (() => void) | null = null

function revokeObjectUrl() {
  revokeCurrentObjectUrl?.()
  revokeCurrentObjectUrl = null
}

watch(
  () => props.src,
  async (src) => {
    revokeObjectUrl()

    if (!src || !isProtectedFileDownloadUrl(src)) {
      displaySrc.value = src
      return
    }

    try {
      const resource = await createProtectedObjectUrl(src)
      displaySrc.value = resource.url
      revokeCurrentObjectUrl = () => resource.revoke()
    } catch {
      displaySrc.value = undefined
    }
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  revokeObjectUrl()
})
</script>
