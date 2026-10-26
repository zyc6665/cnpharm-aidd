<template>
  <main class="targets-list-page" data-testid="targets-list-page">
    <router-link :to="`/projects/${projectId}`" class="back-link">
      {{ t('targets.backToProject') }}
    </router-link>
    <ProjectWorkspaceNav :project-id="projectId" />

    <AppPageHeader :title="t('targets.list.title')" :subtitle="t('targets.list.subtitle')">
      <template #actions>
        <a-button :loading="loading" @click="load">{{ t('targets.refresh') }}</a-button>
        <a-button
          type="primary"
          data-testid="create-target-button"
          @click="openCreateModal"
        >
          {{ t('targets.list.create') }}
        </a-button>
      </template>
    </AppPageHeader>

    <AppErrorState
      v-if="loadError"
      data-testid="targets-list-error"
      code="ERR"
      :title="t('targets.loadFailed')"
      :description="t('targets.loadFailedHint')"
      :action-text="t('targets.backToProject')"
      :to="`/projects/${projectId}`"
    />

    <template v-else>
      <p v-if="!loading && targets.length > 0" class="targets-total" data-testid="targets-total">
        {{ t('targets.list.total', { total }) }}
      </p>

      <SkeletonList v-if="loading && targets.length === 0" :count="4" />

      <a-empty v-else-if="targets.length === 0" class="targets-empty" data-testid="targets-empty">
        <template #description>
          <p class="empty-title">{{ t('targets.list.empty') }}</p>
          <p class="empty-hint">{{ t('targets.list.emptyHint') }}</p>
        </template>
        <a-button type="primary" @click="openCreateModal">
          {{ t('targets.list.create') }}
        </a-button>
      </a-empty>

      <template v-else>
        <a-table
          class="targets-table"
          data-testid="targets-table"
          :columns="columns"
          :data-source="targets"
          :loading="loading"
          :pagination="false"
          row-key="id"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <router-link
                :to="`/targets/${record.id}`"
                class="target-name"
                data-testid="target-name-link"
              >
                {{ record.name }}
              </router-link>
            </template>
            <template v-else-if="column.key === 'targetType'">
              <a-tag v-if="record.target_type" color="blue">{{ record.target_type }}</a-tag>
              <span v-else class="muted">-</span>
            </template>
            <template v-else-if="column.key === 'uniprot'">
              <span class="mono">{{ formatOptionalText(record.uniprot_id) }}</span>
            </template>
            <template v-else-if="column.key === 'gene'">
              {{ formatOptionalText(record.gene_name) }}
            </template>
            <template v-else-if="column.key === 'createdAt'">
              {{ formatTargetDateTime(record.created_at) }}
            </template>
            <template v-else-if="column.key === 'actions'">
              <router-link :to="`/targets/${record.id}`">
                <a-button type="link" size="small" data-testid="target-view-detail">
                  {{ t('targets.viewDetail') }}
                </a-button>
              </router-link>
            </template>
          </template>
        </a-table>

        <a-pagination
          v-if="total > pageSize"
          class="targets-pagination"
          data-testid="targets-pagination"
          :current="page"
          :page-size="pageSize"
          :total="total"
          :show-size-changer="false"
          @change="handlePageChange"
        />
      </template>
    </template>

    <a-modal
      v-model:open="createModalOpen"
      :title="t('targets.list.createTitle')"
      :confirm-loading="creating"
      :ok-text="t('targets.list.create')"
      :cancel-text="t('common.cancel')"
      @ok="handleCreate"
    >
      <a-form layout="vertical" class="target-create-form">
        <a-form-item :label="t('targets.list.name')" required>
          <a-input
            v-model:value="form.name"
            :placeholder="t('targets.list.namePlaceholder')"
            data-testid="target-name-input"
            allow-clear
          />
        </a-form-item>
        <a-form-item :label="t('targets.list.type')">
          <a-input v-model:value="form.targetType" disabled />
        </a-form-item>
        <a-form-item :label="t('targets.list.uniprot')">
          <a-input v-model:value="form.uniprotId" placeholder="P00533" allow-clear />
        </a-form-item>
        <a-form-item :label="t('targets.list.gene')">
          <a-input v-model:value="form.geneName" placeholder="EGFR" allow-clear />
        </a-form-item>
        <a-form-item :label="t('targets.list.description')">
          <a-textarea
            v-model:value="form.description"
            :placeholder="t('targets.list.descriptionPlaceholder')"
            :rows="3"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, reactive, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import { createTarget, listTargets } from '@/api/targets'
  import { formatOptionalText, formatTargetDateTime, resolveTargetErrorMessage } from '@/domain/targets'
  import type { TargetSummary } from '@/types/targets'

  const DEFAULT_PAGE_SIZE = 20

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()

  const projectId = computed(() => String(route.params.projectId || ''))

  const targets = ref<TargetSummary[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(DEFAULT_PAGE_SIZE)
  const loading = ref(false)
  const loadError = ref(false)
  const createModalOpen = ref(false)
  const creating = ref(false)

  const form = reactive({
    name: '',
    targetType: 'PROTEIN',
    uniprotId: '',
    geneName: '',
    description: ''
  })

  const columns = computed(() => [
    { title: t('targets.list.name'), key: 'name' },
    { title: t('targets.list.type'), key: 'targetType', width: 120 },
    { title: t('targets.list.uniprot'), key: 'uniprot', width: 160 },
    { title: t('targets.list.gene'), key: 'gene', width: 140 },
    { title: t('targets.createdAt'), key: 'createdAt', width: 190 },
    { title: t('targets.actions'), key: 'actions', width: 110 }
  ])

  async function load() {
    if (!projectId.value) {
      return
    }
    loading.value = true
    loadError.value = false
    try {
      const response = await listTargets(projectId.value, {
        page: page.value,
        page_size: pageSize.value
      })
      targets.value = response.data.items
      total.value = response.data.total
    } catch {
      loadError.value = true
      targets.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  function handlePageChange(nextPage: number) {
    page.value = nextPage
    void load()
  }

  function openCreateModal() {
    form.name = ''
    form.targetType = 'PROTEIN'
    form.uniprotId = ''
    form.geneName = ''
    form.description = ''
    createModalOpen.value = true
  }

  async function handleCreate() {
    const name = form.name.trim()
    if (!name) {
      message.warning(t('targets.list.nameRequired'))
      return
    }

    creating.value = true
    try {
      const response = await createTarget(projectId.value, {
        name,
        target_type: form.targetType,
        uniprot_id: form.uniprotId.trim() || null,
        gene_name: form.geneName.trim() || null,
        description: form.description.trim() || null
      })
      createModalOpen.value = false
      message.success(t('targets.list.createSuccess'))
      await router.push({ name: 'TargetDetail', params: { targetId: response.data.id } })
    } catch (cause) {
      message.error(resolveTargetErrorMessage(cause, t('targets.list.createFailed')))
    } finally {
      creating.value = false
    }
  }

  onMounted(() => {
    void load()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .targets-list-page {
    max-width: 1080px;
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

  .targets-total {
    margin: 0 0 @spacing-sm;
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .targets-table {
    margin-top: @spacing-sm;
  }

  .target-name {
    color: @accent-color;
    font-weight: @font-weight-medium;
  }

  .muted {
    color: @text-tertiary;
  }

  .mono {
    font-family: @font-family-mono;
    font-size: @font-size-sm;
  }

  .targets-empty {
    padding: @spacing-xxl 0;

    .empty-title {
      margin: 0 0 @spacing-xs;
      color: @text-primary;
      font-size: @font-size-lg;
      font-weight: @font-weight-medium;
    }

    .empty-hint {
      margin: 0 0 @spacing-md;
      color: @text-tertiary;
      font-size: @font-size-sm;
    }
  }

  .targets-pagination {
    margin-top: @spacing-md;
    text-align: right;
  }

  .target-create-form {
    padding-top: @spacing-sm;
  }
</style>
