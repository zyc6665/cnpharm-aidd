<template>
  <main class="compounds-candidates-page">
    <router-link :to="`/projects/${projectId}/assets`" class="back-link">
      {{ t('compounds.candidatesPage.backToAssets') }}
    </router-link>
    <ProjectWorkspaceNav :project-id="projectId" />

    <AppPageHeader
      :title="t('compounds.candidatesPage.title')"
      :subtitle="t('compounds.candidatesPage.subtitle')"
    >
      <template #actions>
        <a-space>
          <a-button
            :loading="loading"
            data-testid="candidates-refresh"
            @click="loadAll"
          >
            {{ t('compounds.actions.refresh') }}
          </a-button>
          <router-link :to="`/projects/${projectId}/candidates/compare`">
            <a-button data-testid="candidates-compare-link">
              {{ t('compounds.actions.compare') }}
            </a-button>
          </router-link>
        </a-space>
      </template>
    </AppPageHeader>

    <AppInlineError
      v-if="loadError"
      class="candidates-alert"
      data-testid="candidates-error"
      :title="t('compounds.errors.loadCandidates')"
      :description="t('common.listStates.errorDescription')"
    >
      <a-button size="small" @click="loadAll">{{ t('common.listStates.retry') }}</a-button>
    </AppInlineError>

    <SkeletonList v-if="loading && !hasAnyRecord" :count="5" />

    <AppEmptyState
      v-else-if="!loadError && !hasAnyRecord"
      :title="t('compounds.empty.candidates')"
      :description="t('compounds.emptyHint.candidates')"
    >
      <router-link :to="`/projects/${projectId}/assets`">
        <a-button>{{ t('compounds.emptyHint.goAssets') }}</a-button>
      </router-link>
      <a-button type="primary" @click="createSetVisible = true">
        {{ t('compounds.actions.createSet') }}
      </a-button>
    </AppEmptyState>

    <template v-else>
      <section class="candidates-section">
        <h3 class="candidates-section-title">{{ t('compounds.tabs.candidates') }}</h3>
        <a-table
          :scroll="{ x: 'max-content' }"
          :columns="candidateColumns"
          :data-source="candidates"
          :pagination="false"
          :locale="{ emptyText: t('compounds.empty.candidates') }"
          row-key="id"
          size="middle"
          data-testid="candidates-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <router-link :to="candidateRoute(record.id)">
                {{ candidateTitle(record) }}
              </router-link>
            </template>
            <template v-else-if="column.key === 'type'">
              <a-tag>{{ t(candidateLocationLabel(record)) }}</a-tag>
            </template>
            <template v-else-if="column.key === 'source'">
              {{ t(`candidates.source.${record.source}`) }}
            </template>
            <template v-else-if="column.key === 'design_score'">
              {{ record.design_score ?? '-' }}
            </template>
            <template v-else-if="column.key === 'created_at'">
              {{ formatDate(record.created_at) }}
            </template>
          </template>
        </a-table>

        <div v-if="candidateTotal > pageSize" class="candidates-pagination">
          <a-pagination
            v-model:current="candidatePage"
            :total="candidateTotal"
            :page-size="pageSize"
            :show-total="(total: number) => t('common.totalItems', { total })"
            @change="loadCandidates"
          />
        </div>
      </section>

      <section class="candidates-section">
        <div class="candidates-section-header">
          <h3 class="candidates-section-title">{{ t('compounds.tabs.candidateSets') }}</h3>
          <a-button
            type="primary"
            data-testid="candidates-create-set-open"
            @click="createSetVisible = true"
          >
            {{ t('compounds.actions.createSet') }}
          </a-button>
        </div>

        <a-table
          :scroll="{ x: 'max-content' }"
          :columns="candidateSetColumns"
          :data-source="candidateSets"
          :pagination="false"
          :locale="{ emptyText: t('compounds.empty.candidateSets') }"
          row-key="id"
          size="middle"
          data-testid="candidates-candidate-set-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <router-link :to="candidateSetRoute(record.id)">
                {{ record.name }}
              </router-link>
            </template>
            <template v-else-if="column.key === 'description'">
              {{ record.description || '-' }}
            </template>
            <template v-else-if="column.key === 'updated_at'">
              {{ formatDate(record.updated_at) }}
            </template>
          </template>
        </a-table>

        <div v-if="setTotal > pageSize" class="candidates-pagination">
          <a-pagination
            v-model:current="setPage"
            :total="setTotal"
            :page-size="pageSize"
            :show-total="(total: number) => t('common.totalItems', { total })"
            @change="loadCandidateSets"
          />
        </div>
      </section>
    </template>

    <!-- 新建候选集 -->
    <a-modal
      v-model:open="createSetVisible"
      :title="t('compounds.set.create.title')"
      :ok-text="t('compounds.set.create.submit')"
      :confirm-loading="creatingSet"
      data-testid="candidates-create-set-modal"
      @ok="submitCreateSet"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('compounds.set.create.name')" required>
          <a-input
            v-model:value="createSetName"
            :placeholder="t('compounds.set.create.namePlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('compounds.set.create.description')">
          <a-textarea
            v-model:value="createSetDescription"
            :rows="3"
            :placeholder="t('compounds.set.create.descriptionPlaceholder')"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import { formatDateTimeMinutes } from '@/utils/datetime'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import AppInlineError from '@/components/common/AppInlineError.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import { createCandidateSet, listCandidateSets, listCandidates } from '@/api/compounds'
  import { candidateLocationLabel } from '@/domain/compounds'
  import type { Candidate, CandidateSet } from '@/types/compounds'

  const route = useRoute()
  const { t } = useI18n()

  const projectId = computed(() => String(route.params.projectId || ''))
  const pageSize = 20

  const projectQuery = computed(() =>
    projectId.value ? `?project_id=${encodeURIComponent(projectId.value)}` : ''
  )

  function candidateRoute(id: string): string {
    return `/candidates/${encodeURIComponent(id)}${projectQuery.value}`
  }

  function candidateSetRoute(id: string): string {
    return `/candidate-sets/${encodeURIComponent(id)}${projectQuery.value}`
  }

  const loading = ref(false)
  const loadError = ref(false)

  const candidates = ref<Candidate[]>([])
  const candidateTotal = ref(0)
  const candidatePage = ref(1)

  const candidateSets = ref<CandidateSet[]>([])
  const setTotal = ref(0)
  const setPage = ref(1)

  const hasAnyRecord = computed(
    () => candidates.value.length > 0 || candidateSets.value.length > 0
  )

  const candidateColumns = computed(() => [
    { title: t('candidates.fields.name'), key: 'name', width: 220 },
    { title: t('candidates.fields.type'), key: 'type', width: 120 },
    { title: t('candidates.fields.source'), key: 'source', width: 120 },
    { title: t('candidates.fields.designScore'), key: 'design_score', width: 120 },
    { title: t('candidates.fields.createdAt'), key: 'created_at', width: 160 }
  ])

  const candidateSetColumns = computed(() => [
    { title: t('compounds.set.columns.name'), key: 'name', width: 220 },
    { title: t('compounds.set.columns.description'), key: 'description' },
    { title: t('compounds.set.columns.itemCount'), dataIndex: 'item_count', key: 'item_count', width: 100 },
    { title: t('compounds.set.columns.version'), dataIndex: 'version', key: 'version', width: 90 },
    { title: t('compounds.set.columns.updatedAt'), key: 'updated_at', width: 160 }
  ])

  const createSetVisible = ref(false)
  const creatingSet = ref(false)
  const createSetName = ref('')
  const createSetDescription = ref('')

  function formatDate(value: string | null | undefined): string {
    return value ? formatDateTimeMinutes(value) : '-'
  }

  function candidateTitle(candidate: Candidate): string {
    return candidate.name || candidate.code || candidate.peptide_sequence || candidate.id
  }

  function optionalText(value: string): string | undefined {
    const trimmed = value.trim()
    return trimmed ? trimmed : undefined
  }

  async function loadCandidates(): Promise<void> {
    if (!projectId.value) return
    const response = await listCandidates(projectId.value, {
      page: candidatePage.value,
      page_size: pageSize
    })
    candidates.value = response.data.items
    candidateTotal.value = response.data.total
  }

  async function loadCandidateSets(): Promise<void> {
    if (!projectId.value) return
    const response = await listCandidateSets(projectId.value, {
      page: setPage.value,
      page_size: pageSize
    })
    candidateSets.value = response.data.items
    setTotal.value = response.data.total
  }

  async function loadAll(): Promise<void> {
    if (!projectId.value) return
    loading.value = true
    loadError.value = false
    const settled = await Promise.allSettled([loadCandidates(), loadCandidateSets()])
    loadError.value = settled.some(result => result.status === 'rejected')
    loading.value = false
  }

  async function submitCreateSet(): Promise<void> {
    const name = createSetName.value.trim()
    if (!name) {
      message.warning(t('compounds.set.create.name'))
      return
    }

    creatingSet.value = true
    try {
      const description = optionalText(createSetDescription.value)
      await createCandidateSet(projectId.value, {
        name,
        ...(description ? { description } : {})
      })
      message.success(t('compounds.set.create.success'))
      createSetVisible.value = false
      createSetName.value = ''
      createSetDescription.value = ''
      setPage.value = 1
      await loadCandidateSets()
    } catch {
      message.error(t('common.error'))
    } finally {
      creatingSet.value = false
    }
  }

  onMounted(() => {
    void loadAll()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .compounds-candidates-page {
    max-width: 1240px;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;
  }

  .candidates-alert {
    margin-bottom: @spacing-lg;
  }

  .candidates-section {
    margin-bottom: @spacing-xxl;
  }

  .candidates-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
  }

  .candidates-section-title {
    margin: 0 0 @spacing-md;
    font-size: @font-size-lg;
  }

  .candidates-pagination {
    display: flex;
    justify-content: flex-end;
    margin-top: @spacing-md;
  }
</style>
