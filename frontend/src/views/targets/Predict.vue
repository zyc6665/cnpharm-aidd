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
  import { computed, onMounted, reactive, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import { getProtein, predictStructure } from '@/api/targets'
  import { resolveTargetErrorMessage } from '@/domain/targets'
  import type { ProteinDetail } from '@/types/targets'

  const DEFAULT_MODEL = 'boltz-2'
  const DEFAULT_NUM_RECYCLES = 3
  const DEFAULT_SEED = 42
  const DEFAULT_USE_MSA = false

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()

  const proteinId = computed(() => String(route.params.proteinId || ''))
  const protein = ref<ProteinDetail | null>(null)
  const loading = ref(false)
  const loadError = ref(false)
  const submitting = ref(false)

  const form = reactive({
    modelName: DEFAULT_MODEL,
    numRecycles: DEFAULT_NUM_RECYCLES,
    seed: DEFAULT_SEED,
    useMsa: DEFAULT_USE_MSA
  })

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

  function normalizeNumber(value: number | string | null | undefined, fallback: number): number {
    const parsed = typeof value === 'number' ? value : Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }

  async function handleSubmit() {
    const modelName = form.modelName.trim() || DEFAULT_MODEL
    const numRecycles = normalizeNumber(form.numRecycles, DEFAULT_NUM_RECYCLES)
    const seed = normalizeNumber(form.seed, DEFAULT_SEED)

    if (numRecycles < 1 || seed < 0) {
      message.warning(t('targets.predict.invalidNumber'))
      return
    }

    submitting.value = true
    try {
      // 键名按 docs/05 §5.1 与 docs/16 的口径（camelCase）；后端 `params` 直接透传，
      // 没有 snake↔camel 转换层，写成 num_recycles 工具侧会读不到。
      const response = await predictStructure(proteinId.value, {
        model_ref: { name: modelName },
        params: {
          useMsa: form.useMsa,
          numRecycles,
          seed
        }
      })
      message.success(t('targets.predict.submitted'))
      await router.push({ name: 'TaskDetail', params: { id: response.data.task_id } })
    } catch (cause) {
      message.error(resolveTargetErrorMessage(cause, t('targets.predict.failed')))
    } finally {
      submitting.value = false
    }
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
