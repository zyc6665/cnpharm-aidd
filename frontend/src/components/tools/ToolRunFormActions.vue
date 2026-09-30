<template>
  <a-form-item class="tool-form-actions">
    <a-space wrap>
      <a-button
        v-if="loginRequired"
        type="primary"
        size="large"
        @click="emit('login')"
      >
        <LoginOutlined />
        {{ t('auth.goLogin') }}
      </a-button>
      <a-tooltip v-else-if="disabledReason" :title="disabledReason">
        <span>
          <a-button
            type="primary"
            html-type="submit"
            size="large"
            :loading="submitting"
            :disabled="!canSubmit"
          >
            <PlayCircleOutlined />
            {{ t('tools.runTool') }}
          </a-button>
        </span>
      </a-tooltip>
      <a-button
        v-else
        type="primary"
        html-type="submit"
        size="large"
        :loading="submitting"
        :disabled="!canSubmit"
      >
        <PlayCircleOutlined />
        {{ t('tools.runTool') }}
      </a-button>
      <a-button size="large" @click="emit('reset')">
        {{ t('common.reset') }}
      </a-button>
    </a-space>
  </a-form-item>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import { LoginOutlined, PlayCircleOutlined } from '@ant-design/icons-vue'

  defineProps<{
    submitting: boolean
    canSubmit: boolean
    disabledReason?: string
    loginRequired?: boolean
  }>()

  const emit = defineEmits<{
    reset: []
    login: []
  }>()

  const { t } = useI18n()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-form-actions {
    margin-bottom: 0;

    @media (max-width: @screen-md) {
      :deep(.ant-space) {
        width: 100%;
      }

      :deep(.ant-btn) {
        width: 100%;
      }
    }
  }
</style>
