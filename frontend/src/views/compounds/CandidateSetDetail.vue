<template>
  <main class="candidate-set-page">
    <AppPageHeader :title="setTitle" :subtitle="t('candidates.set.subtitle')">
      <template #actions>
        <a-space>
          <a-button :loading="loading" data-testid="set-refresh" @click="refreshAll">
            {{ t('candidates.set.actions.refreshing') }}
          </a-button>
          <a-button data-testid="set-edit-open" @click="openEditModal">
            {{ t('common.edit') }}
          </a-button>
          <a-button
            :loading="exporting"
            data-testid="set-export"
            @click="handleExport"
          >
            {{ t('candidates.set.actions.export') }}
          </a-button>
        </a-space>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="conflictVersion !== null"
      class="set-alert"
      type="warning"
      show-icon
      data-testid="set-conflict"
      :message="t('candidates.set.conflictTitle')"
      :description="t('candidates.set.conflictDescription', { version: conflictVersion })"
    >
      <template #action>
        <a-button size="small" data-testid="set-conflict-refresh" @click="refreshAll">
          {{ t('candidates.set.conflictRefresh') }}
        </a-button>
      </template>
    </a-alert>

    <a-alert
      v-if="loadError"
      class="set-alert"
      type="error"
      show-icon
      data-testid="set-error"
      :message="t('candidates.set.errors.load')"
    >
      <template #action>
        <a-button size="small" @click="refreshAll">{{ t('common.refresh') }}</a-button>
      </template>
    </a-alert>

    <SkeletonDetail v-if="loading && !candidateSet" />

    <template v-else-if="candidateSet">
      <a-descriptions
        bordered
        :column="2"
        size="small"
        class="set-info"
        data-testid="set-info"
      >
        <a-descriptions-item :label="t('compounds.set.columns.name')">
          {{ candidateSet.name }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('candidates.set.version')">
          <span data-testid="set-version">v{{ candidateSet.version }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('candidates.set.itemCount')">
          {{ candidateSet.item_count }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('candidates.set.sourceTask')">
          <router-link
            v-if="candidateSet.source_task_id"
            :to="`/tasks/${candidateSet.source_task_id}`"
          >
            {{ candidateSet.source_task_id }}
          </router-link>
          <span v-else>-</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('candidates.set.description')" :span="2">
          {{ candidateSet.description || '-' }}
        </a-descriptions-item>
      </a-descriptions>

      <section class="set-section">
        <div class="set-toolbar">
          <h3 class="section-title">{{ t('candidates.set.info') }}</h3>
          <a-button
            type="primary"
            data-testid="set-add-open"
            @click="openAddModal"
          >
            {{ t('candidates.set.actions.addItems') }}
          </a-button>
        </div>

        <a-alert
          v-if="itemsError"
          class="set-alert"
          type="error"
          show-icon
          data-testid="set-items-error"
          :message="t('candidates.set.errors.loadItems')"
        />

        <a-table
          :columns="itemColumns"
          :data-source="items"
          :pagination="false"
          :locale="{ emptyText: t('candidates.set.empty') }"
          row-key="id"
          size="middle"
          data-testid="set-item-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'ordinal'">
              {{ record.ordinal }}
            </template>
            <template v-else-if="column.key === 'name'">
              <router-link v-if="record.candidate" :to="`/candidates/${record.candidate.id}`">
                {{ candidateTitle(record.candidate) }}
              </router-link>
              <span v-else>{{ record.candidate_id }}</span>
            </template>
            <template v-else-if="column.key === 'type'">
              <a-tag>{{ t(candidateLocationLabel(record)) }}</a-tag>
            </template>
            <template v-else-if="column.key === 'design_score'">
              {{ record.candidate?.design_score ?? '-' }}
            </template>
            <template v-else-if="column.key === 'snapshot_score'">
              {{ record.snapshot_score ?? '-' }}
            </template>
            <template v-else-if="column.key === 'actions'">
              <a-popconfirm
                :title="t('candidates.set.removeConfirm')"
                @confirm="handleRemove(record.id)"
              >
                <a-button
                  type="link"
                  danger
                  size="small"
                  data-testid="set-remove-item"
                >
                  {{ t('candidates.set.actions.removeItem') }}
                </a-button>
              </a-popconfirm>
            </template>
          </template>
        </a-table>

        <div v-if="itemTotal > itemPageSize" class="set-pagination">
          <a-pagination
            v-model:current="itemPage"
            :total="itemTotal"
            :page-size="itemPageSize"
            :show-total="(total: number) => t('common.totalItems', { total })"
            @change="loadItems"
          />
        </div>
      </section>
    </template>

    <p v-else class="section-empty" data-testid="set-not-found">
      {{ t('candidates.set.errors.load') }}
    </p>

    <a-modal
      v-model:open="editVisible"
      :title="t('candidates.set.editTitle')"
      :ok-text="t('common.save')"
      :confirm-loading="saving"
      data-testid="set-edit-modal"
      @ok="handleSave"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('compounds.set.columns.name')" required>
          <a-input v-model:value="editName" data-testid="set-edit-name" />
        </a-form-item>
        <a-form-item :label="t('candidates.set.description')">
          <a-textarea v-model:value="editDescription" :rows="3" />
        </a-form-item>
      </a-form>
      <p class="edit-version">
        {{ t('candidates.set.version') }}: v{{ candidateSet?.version ?? '-' }}
      </p>
    </a-modal>

    <a-modal
      v-model:open="addVisible"
      :title="t('candidates.set.addTitle')"
      :ok-text="t('candidates.set.addSubmit')"
      :confirm-loading="adding"
      data-testid="set-add-modal"
      @ok="handleAdd"
    >
      <a-select
        v-model:value="selectedCandidateIds"
        mode="multiple"
        class="add-select"
        :placeholder="t('candidates.set.addPlaceholder')"
        :loading="candidateOptionsLoading"
        :options="candidateOptions"
        data-testid="set-add-select"
      />
      <p v-if="candidateOptionsError" class="add-error">
        {{ t('candidates.set.errors.loadCandidates') }}
      </p>
    </a-modal>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import { isAxiosError } from 'axios'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import {
    addCandidateSetItems,
    exportCandidateSet,
    getCandidateSet,
    listCandidateSetItems,
    listCandidates,
    removeCandidateSetItem,
    updateCandidateSet
  } from '@/api/compounds'
  import { candidateLocationLabel } from '@/domain/compounds'
  import type { Candidate, CandidateSet as CandidateSetModel, CandidateSetItem } from '@/types/compounds'

  interface SelectOption {
    label: string
    value: string
  }

  const route = useRoute()
  const { t } = useI18n()

  const setId = computed(() => String(route.params.setId || ''))

  const loading = ref(false)
  const loadError = ref(false)
  const itemsError = ref(false)
  const candidateSet = ref<CandidateSetModel | null>(null)
  const items = ref<CandidateSetItem[]>([])
  const itemTotal = ref(0)
  const itemPage = ref(1)
  const itemPageSize = 50

  const exporting = ref(false)
  const conflictVersion = ref<number | null>(null)

  const addVisible = ref(false)
  const adding = ref(false)
  const selectedCandidateIds = ref<string[]>([])
  const candidateOptions = ref<SelectOption[]>([])
  const candidateOptionsLoading = ref(false)
  const candidateOptionsError = ref(false)

  const editVisible = ref(false)
  const saving = ref(false)
  const editName = ref('')
  const editDescription = ref('')

  const setTitle = computed(() => candidateSet.value?.name || t('candidates.set.title'))

  const itemColumns = computed(() => [
    { title: t('candidates.set.columns.ordinal'), key: 'ordinal', width: 80 },
    { title: t('candidates.set.columns.name'), key: 'name', width: 220 },
    { title: t('candidates.set.columns.type'), key: 'type', width: 120 },
    { title: t('candidates.set.columns.designScore'), key: 'design_score', width: 120 },
    { title: t('candidates.set.columns.snapshotScore'), key: 'snapshot_score', width: 120 },
    { title: t('common.actions'), key: 'actions', width: 100 }
  ])

  function candidateTitle(candidate: Candidate): string {
    return candidate.name || candidate.code || candidate.peptide_sequence || candidate.id
  }

  function readCurrentVersion(error: unknown): number | null {
    if (!isAxiosError(error) || error.response?.status !== 409) {
      return null
    }
    const detail = error.response.data as { detail?: { currentVersion?: number } } | undefined
    const version = detail?.detail?.currentVersion
    return typeof version === 'number' ? version : null
  }

  async function loadSet(): Promise<void> {
    if (!setId.value) return
    loadError.value = false
    try {
      const response = await getCandidateSet(setId.value)
      candidateSet.value = response.data
    } catch {
      loadError.value = true
      candidateSet.value = null
    }
  }

  async function loadItems(): Promise<void> {
    if (!setId.value) return
    itemsError.value = false
    try {
      const response = await listCandidateSetItems(setId.value, {
        page: itemPage.value,
        page_size: itemPageSize
      })
      items.value = response.data.items
      itemTotal.value = response.data.total
    } catch {
      itemsError.value = true
      items.value = []
      itemTotal.value = 0
    }
  }

  async function refreshAll(): Promise<void> {
    if (!setId.value) return
    loading.value = true
    conflictVersion.value = null
    const settled = await Promise.allSettled([loadSet(), loadItems()])
    loadError.value = settled[0]?.status === 'rejected'
    loading.value = false
  }

  async function loadCandidateOptions(): Promise<void> {
    const projectId = candidateSet.value?.project_id
    if (!projectId) return

    candidateOptionsLoading.value = true
    candidateOptionsError.value = false
    try {
      const response = await listCandidates(projectId, { page: 1, page_size: 200 })
      candidateOptions.value = response.data.items.map(candidate => ({
        label: candidateTitle(candidate),
        value: candidate.id
      }))
    } catch {
      candidateOptionsError.value = true
      candidateOptions.value = []
    } finally {
      candidateOptionsLoading.value = false
    }
  }

  function openAddModal(): void {
    addVisible.value = true
    selectedCandidateIds.value = []
    void loadCandidateOptions()
  }

  function openEditModal(): void {
    editName.value = candidateSet.value?.name ?? ''
    editDescription.value = candidateSet.value?.description ?? ''
    editVisible.value = true
  }

  async function handleSave(): Promise<void> {
    const current = candidateSet.value
    if (!current) return

    const name = editName.value.trim()
    if (!name) {
      return
    }

    saving.value = true
    try {
      await updateCandidateSet(setId.value, {
        name,
        description: editDescription.value.trim(),
        version: current.version,
        expected_version: current.version
      })
      message.success(t('common.success'))
      editVisible.value = false
      await refreshAll()
    } catch (error) {
      const version = readCurrentVersion(error)
      if (version !== null) {
        conflictVersion.value = version
        editVisible.value = false
      } else {
        message.error(t('common.error'))
      }
    } finally {
      saving.value = false
    }
  }

  async function handleAdd(): Promise<void> {
    if (selectedCandidateIds.value.length === 0) {
      return
    }

    adding.value = true
    try {
      const response = await addCandidateSetItems(setId.value, {
        candidate_ids: selectedCandidateIds.value
      })
      message.success(t('candidates.set.addSuccess', { count: response.data.inserted }))
      addVisible.value = false
      selectedCandidateIds.value = []
      await refreshAll()
    } catch (error) {
      const version = readCurrentVersion(error)
      if (version !== null) {
        conflictVersion.value = version
        addVisible.value = false
      } else {
        message.error(t('common.error'))
      }
    } finally {
      adding.value = false
    }
  }

  async function handleRemove(itemId: string): Promise<void> {
    try {
      await removeCandidateSetItem(setId.value, itemId)
      message.success(t('candidates.set.removeSuccess'))
      await refreshAll()
    } catch (error) {
      const version = readCurrentVersion(error)
      if (version !== null) {
        conflictVersion.value = version
      } else {
        message.error(t('common.error'))
      }
    }
  }

  function triggerBlobDownload(content: string, filename: string): void {
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    try {
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
    } finally {
      anchor.remove()
      URL.revokeObjectURL(url)
    }
  }

  async function handleExport(): Promise<void> {
    if (!candidateSet.value) return

    exporting.value = true
    try {
      const response = await exportCandidateSet(setId.value)
      const payload = response.data
      if (payload.content) {
        triggerBlobDownload(payload.content, `${candidateSet.value.name}.csv`)
      } else if (payload.download_url) {
        const { triggerProtectedFileDownload } = await import('@/utils/protected-file-access')
        await triggerProtectedFileDownload({
          url: payload.download_url,
          filename: `${candidateSet.value.name}.csv`
        })
      }
      message.success(t('candidates.set.exportSuccess'))
    } catch {
      message.error(t('candidates.set.errors.export'))
    } finally {
      exporting.value = false
    }
  }

  onMounted(() => {
    void refreshAll()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .candidate-set-page {
    max-width: 1240px;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .set-alert {
    margin-bottom: @spacing-md;
  }

  .set-info {
    margin-bottom: @spacing-xl;
  }

  .set-section {
    margin-top: @spacing-xl;
  }

  .set-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: @spacing-md;
  }

  .section-title {
    margin: 0;
    color: @text-primary;
    font-size: @font-size-lg;
  }

  .set-pagination {
    display: flex;
    justify-content: flex-end;
    margin-top: @spacing-md;
  }

  .section-empty {
    padding: @spacing-lg;
    color: @text-tertiary;
    text-align: center;
    background: @bg-surface;
    border: 1px dashed @border-color;
    border-radius: @border-radius-md;
  }

  .add-select {
    width: 100%;
  }

  .add-error {
    margin-top: @spacing-sm;
    color: @error-color;
    font-size: @font-size-xs;
  }
</style>
