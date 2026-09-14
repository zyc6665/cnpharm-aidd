<template>
  <a-space class="tool-detail-actions" wrap>
    <a-button @click="emit('view-documentation')">
      <InfoCircleOutlined />
      {{ t('tools.viewIntroduction') }}
    </a-button>
    <a-button
      :type="tool.is_favorited ? 'primary' : 'default'"
      :loading="favoriteLoading"
      @click="emit('toggle-favorite')"
    >
      <HeartFilled v-if="tool.is_favorited" />
      <HeartOutlined v-else />
      {{ tool.is_favorited ? t('tools.unfavorite') : t('tools.favorite') }}
    </a-button>
    <a-tag v-if="tool.current_version" color="blue">
      v{{ tool.current_version.version }}
    </a-tag>
  </a-space>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import {
    HeartOutlined,
    HeartFilled,
    InfoCircleOutlined,
  } from '@ant-design/icons-vue'
  import type { Tool } from '@/types/models'

  defineProps<{
    tool: Tool
    favoriteLoading: boolean
  }>()

  const emit = defineEmits<{
    'view-documentation': []
    'toggle-favorite': []
  }>()

  const { t } = useI18n()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-detail-actions {
    align-items: center;
    justify-content: flex-end;

    @media (max-width: @screen-md) {
      justify-content: flex-start;
      width: 100%;
    }
  }
</style>
