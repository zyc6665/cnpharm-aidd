<template>
  <main class="structure-detail-page" data-testid="structure-detail-page">
    <router-link :to="backLink" class="back-link">
      {{ t('targets.structure.backToTarget') }}
    </router-link>

    <AppPageHeader :title="t('targets.structure.title')" :subtitle="t('targets.structure.subtitle')">
      <template #actions>
        <a-button :loading="loading" @click="load">{{ t('targets.refresh') }}</a-button>
        <a-button
          type="primary"
          :loading="pocketSubmitting"
          data-testid="predict-pockets-button"
          @click="handlePredictPockets"
        >
          {{ t('targets.structure.predictPockets') }}
        </a-button>
      </template>
    </AppPageHeader>

    <AppErrorState
      v-if="loadError"
      data-testid="structure-detail-error"
      code="ERR"
      :title="t('targets.loadFailed')"
      :description="t('targets.loadFailedHint')"
      :action-text="t('targets.structure.backToTarget')"
    />

    <SkeletonDetail v-else-if="loading && !structure" />

    <template v-else-if="structure">
      <div class="structure-layout">
        <section class="preview-column" data-testid="structure-preview">
          <h2 class="section-title">{{ t('targets.structure.preview') }}</h2>
          <StructureArtifactPreview
            v-if="previewArtifact"
            :artifact="previewArtifact"
            :preferred-file-roles="previewFileRoles"
          />
          <a-empty v-else :description="t('targets.structure.previewEmpty')" />
        </section>

        <aside class="info-column">
          <a-descriptions
            class="structure-info"
            data-testid="structure-info"
            :title="t('targets.structure.info')"
            :column="1"
            size="small"
            bordered
          >
            <a-descriptions-item :label="t('targets.structure.protein')">
              <router-link
                v-if="backTargetId"
                :to="`/targets/${backTargetId}`"
                data-testid="structure-target-link"
              >
                {{ structure.protein_id }}
              </router-link>
              <span v-else class="mono">{{ structure.protein_id }}</span>
            </a-descriptions-item>
            <a-descriptions-item :label="t('targets.structure.sourceType')">
              {{ formatOptionalText(structure.source_type) }}
            </a-descriptions-item>
            <a-descriptions-item :label="t('targets.structure.plddt')">
              <span data-testid="structure-plddt">{{ formatPlddtMean(structure.plddt_mean) }}</span>
            </a-descriptions-item>
            <a-descriptions-item :label="t('targets.structure.model')">
              {{ formatToolRef(structure.model) }}
            </a-descriptions-item>
            <a-descriptions-item :label="t('targets.structure.tool')">
              {{ formatToolRef(structure.tool) }}
            </a-descriptions-item>
            <a-descriptions-item :label="t('targets.structure.sha256')">
              <span class="mono sha">{{ formatOptionalText(structure.sha256) }}</span>
            </a-descriptions-item>
            <a-descriptions-item :label="t('targets.structure.taskId')">
              <span class="mono">{{ formatOptionalText(structure.task_id) }}</span>
            </a-descriptions-item>
          </a-descriptions>

          <section class="pocket-section" data-testid="structure-pockets">
            <div class="pocket-head">
              <h2 class="section-title">
                {{ t('targets.structure.pockets', { count: pockets.length }) }}
              </h2>
              <router-link
                v-if="pockets.length > 0"
                :to="`/structures/${structure.id}/pockets`"
                data-testid="view-all-pockets"
              >
                {{ t('targets.structure.viewAllPockets') }}
              </router-link>
            </div>

            <a-empty
              v-if="pockets.length === 0"
              :description="t('targets.structure.pocketsEmpty')"
            />
            <ul v-else class="pocket-list">
              <li v-for="pocket in pockets" :key="pocket.id" class="pocket-item">
                <router-link
                  :to="`/pockets/${pocket.id}/residues`"
                  data-testid="pocket-residues-link"
                >
                  <span class="pocket-rank">#{{ pocket.rank ?? '-' }}</span>
                  <span class="pocket-score" :class="`tone-${pocketScoreTone(pocket.score)}`">
                    {{ formatPocketScore(pocket.score) }}
                  </span>
                  <span class="pocket-meta">
                    {{ pocket.residue_count ?? '-' }} {{ t('targets.pockets.residueCount') }}
                  </span>
                </router-link>
                <a-tag v-if="pocket.selected" color="green" class="pocket-selected">
                  {{ t('targets.pockets.selectedBadge') }}
                </a-tag>
              </li>
            </ul>
          </section>
        </aside>
      </div>
    </template>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import StructureArtifactPreview from '@/components/artifacts/StructureArtifactPreview.vue'
  import {
    getProtein,
    getStructure,
    getStructurePdbManifest,
    predictPockets
  } from '@/api/targets'
  import {
    buildStructurePreviewArtifact,
    formatOptionalText,
    formatPlddtMean,
    formatPocketScore,
    formatToolRef,
    pocketScoreTone,
    sortPocketsByScore,
    STRUCTURE_PREVIEW_FILE_ROLES
  } from '@/domain/targets'
  import type {
    PocketSummary,
    ProteinStructureDetail,
    StructureFileLink
  } from '@/types/targets'

  const route = useRoute()
  const { t } = useI18n()

  const structureId = computed(() => String(route.params.structureId || ''))
  const structure = ref<ProteinStructureDetail | null>(null)
  const structureFiles = ref<StructureFileLink[]>([])
  const loading = ref(false)
  const loadError = ref(false)
  const pocketSubmitting = ref(false)

  const pockets = computed<PocketSummary[]>(() =>
    sortPocketsByScore(structure.value?.pockets ?? [])
  )

  const previewArtifact = computed(() => {
    if (!structure.value) {
      return null
    }
    return buildStructurePreviewArtifact(structure.value, structureFiles.value)
  })

  const backTargetId = ref('')

  const previewFileRoles = [...STRUCTURE_PREVIEW_FILE_ROLES]

  async function loadFiles(id: string) {
    try {
      const response = await getStructurePdbManifest(id)
      structureFiles.value = response.data.files
    } catch {
      structureFiles.value = []
    }
  }

  async function loadTargetContext(proteinId: string) {
    try {
      const response = await getProtein(proteinId)
      backTargetId.value = response.data.target_id
    } catch {
      backTargetId.value = ''
    }
  }

  async function load() {
    if (!structureId.value) {
      return
    }
    loading.value = true
    loadError.value = false
    try {
      const response = await getStructure(structureId.value)
      structure.value = response.data
      backTargetId.value = ''
      await Promise.all([
        loadFiles(response.data.id),
        loadTargetContext(response.data.protein_id)
      ])
    } catch {
      loadError.value = true
      structure.value = null
      structureFiles.value = []
    } finally {
      loading.value = false
    }
  }

  async function handlePredictPockets() {
    if (!structure.value) {
      return
    }
    pocketSubmitting.value = true
    try {
      const response = await predictPockets(structure.value.id, {
        model_ref: { name: 'lvpocket-pocket-prediction' },
        params: {}
      })
      message.success(
        `${t('targets.structure.pocketsSubmitted')} (${response.data.task_id})`
      )
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : t('targets.structure.pocketsFailed'))
    } finally {
      pocketSubmitting.value = false
    }
  }

  const backLink = computed(() =>
    backTargetId.value ? `/targets/${backTargetId.value}` : '/'
  )

  onMounted(() => {
    void load()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .structure-detail-page {
    max-width: 1180px;
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

  .structure-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr);
    gap: @spacing-lg;

    @media (max-width: @screen-md) {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  .section-title {
    margin: 0 0 @spacing-sm;
    color: @text-primary;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
  }

  .pocket-section {
    margin-top: @spacing-lg;
  }

  .pocket-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: @spacing-sm;
  }

  .pocket-list {
    margin: 0;
    padding: 0;
    list-style: none;

    li {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: @spacing-sm;
      padding: @spacing-xs 0;
      border-bottom: 1px dashed @border-color;
    }

    a {
      display: flex;
      align-items: center;
      gap: @spacing-sm;
      color: @text-secondary;
    }
  }

  .pocket-rank {
    color: @text-tertiary;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
  }

  .pocket-score {
    font-family: @font-family-mono;
    font-weight: @font-weight-semibold;

    &.tone-strong {
      color: @success-color;
    }

    &.tone-medium {
      color: @warning-color;
    }

    &.tone-weak {
      color: @text-tertiary;
    }
  }

  .pocket-meta {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .mono {
    font-family: @font-family-mono;
    font-size: @font-size-xs;
  }

  .sha {
    word-break: break-all;
  }
</style>
