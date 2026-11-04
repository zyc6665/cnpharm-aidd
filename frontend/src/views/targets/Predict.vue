<template>
  <main class="structure-predict-page" data-testid="structure-predict-page">
    <router-link :to="backLink" class="back-link">
      {{ t('targets.predict.backToTarget') }}
    </router-link>

    <AppPageHeader :title="t('targets.predict.title')" :subtitle="t('targets.predict.subtitle')" />

    <AppErrorState
      v-if="loadError"
      data-testid="structure-predict-error"
      code="ERR"
      :title="t('targets.loadFailed')"
      :description="t('targets.loadFailedHint')"
      :action-text="t('targets.predict.backToTarget')"
      :to="backLink"
    />

    <SkeletonDetail v-else-if="loading && !protein" />

    <template v-else>
      <a-alert
        v-if="sequenceMissing"
        class="predict-alert"
        type="warning"
        show-icon
        :message="t('targets.predict.sequenceMissing')"
        data-testid="predict-sequence-missing"
      />

      <a-descriptions
        class="protein-summary"
        data-testid="predict-protein-summary"
        :column="2"
        size="small"
        bordered
      >
        <a-descriptions-item :label="t('targets.detail.name')">
          {{ protein ? protein.name : '-' }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('targets.detail.seqLength')">
          {{ protein?.seq_length ?? '-' }}
        </a-descriptions-item>
      </a-descriptions>

      <a-form class="predict-form" layout="vertical" data-testid="predict-form">
        <a-form-item :label="t('targets.predict.model')">
          <a-input v-model:value="form.modelName" data-testid="predict-model-input" />
        </a-form-item>
        <a-form-item :label="t('targets.predict.numRecycles')">
          <a-input-number
            v-model:value="form.numRecycles"
            class="number-input"
            :min="1"
            :max="20"
            :precision="0"
            data-testid="predict-num-recycles"
          />
        </a-form-item>
        <a-form-item :label="t('targets.predict.seed')">
          <a-input-number
            v-model:value="form.seed"
            class="number-input"
            :min="0"
            :precision="0"
            data-testid="predict-seed"
          />
        </a-form-item>
        <a-form-item :label="t('targets.predict.useMsa')" :extra="t('targets.predict.useMsaHint')">
          <a-switch v-model:checked="form.useMsa" data-testid="predict-use-msa" />
        </a-form-item>

        <p class="resource-note" data-testid="predict-resource-note">
          <a-typography-text type="secondary">
            {{ t('targets.predict.resourceManagedByPlatform') }}
          </a-typography-text>
        </p>

        <div class="predict-actions">
          <a-button
            type="primary"
            :loading="submitting"
            :disabled="sequenceMissing"
            data-testid="predict-submit"
            @click="handleSubmit"
          >
            {{ t('targets.predict.submit') }}
          </a-button>
        </div>
      </a-form>
    </template>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import { getProtein } from '@/api/targets'
  import { useStructurePrediction } from '@/composables/useStructurePrediction'
  import type { ProteinDetail } from '@/types/targets'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()

  const proteinId = computed(() => String(route.params.proteinId || ''))
  const protein = ref<ProteinDetail | null>(null)
  const loading = ref(false)
  const loadError = ref(false)

  // 与「上游接力条」共用同一套结构预测表单/提交逻辑，避免两份实现漂移。
  const { form, submitting, error, submit } = useStructurePrediction()

  const sequenceMissing = computed(() => {
    if (!protein.value) {
      return false
    }
    return !protein.value.sequence || protein.value.sequence.trim().length === 0
  })

  const backLink = computed(() => {
    const targetId = protein.value?.target_id
    return targetId ? `/targets/${targetId}` : '/'
  })

  async function load() {
    if (!proteinId.value) {
      return
    }
    loading.value = true
    loadError.value = false
    try {
      const response = await getProtein(proteinId.value)
      protein.value = response.data
    } catch {
      loadError.value = true
      protein.value = null
    } finally {
      loading.value = false
    }
  }

  async function handleSubmit() {
    const taskId = await submit(proteinId.value)
    if (!taskId) {
      message.warning(
        error.value === 'submit-failed'
          ? t('targets.predict.failed')
          : t('targets.predict.invalidNumber')
      )
      return
    }
    message.success(t('targets.predict.submitted'))
    await router.push({ name: 'TaskDetail', params: { id: taskId } })
  }

  onMounted(() => {
    void load()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .structure-predict-page {
    max-width: 640px;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;

    &:hover {
      color: @accent-color;
    }
  }

  .predict-alert {
    margin-bottom: @spacing-md;
  }

  .protein-summary {
    margin-bottom: @spacing-lg;
  }

  .predict-form {
    padding: @spacing-lg;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-surface;
  }

  .number-input {
    width: 180px;
  }

  .resource-note {
    margin: 0 0 @spacing-md;
    font-size: @font-size-sm;
  }

  .predict-actions {
    display: flex;
    justify-content: flex-end;
  }
</style>
