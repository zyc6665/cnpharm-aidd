<template>
  <section class="pocket-complex" data-testid="pocket-complex-viewer">
    <header class="pocket-complex__header">
      <div>
        <h4>{{ t('tasks.resultPage.pocketComplexTitle') }}</h4>
        <p>{{ t('tasks.resultPage.pocketComplexHint') }}</p>
      </div>
      <div class="pocket-complex__legend">
        <span class="pocket-complex__legend-item pocket-complex__legend-item--protein">
          {{ t('tasks.resultPage.legendProtein') }}
        </span>
        <span class="pocket-complex__legend-item pocket-complex__legend-item--pocket">
          {{ t('tasks.resultPage.legendPocket') }}
        </span>
        <span class="pocket-complex__legend-item pocket-complex__legend-item--voxel">
          {{ t('tasks.resultPage.legendVoxel') }}
        </span>
      </div>
    </header>

    <MoleculeViewer
      v-if="scene"
      :scene="scene"
      :voxel-grid="voxelGrid"
    />
    <a-alert
      v-else
      type="warning"
      show-icon
      :message="t('tasks.resultPage.proteinStructureMissing')"
    />
  </section>
</template>

<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import MoleculeViewer from '@/components/tasks/MoleculeViewer.vue'
  import type { VisualizationScene, VisualizationSceneEntry } from '@/domain/tasks'
  import { parsePocketVoxelBoxes, type PocketVoxelGrid } from '@/domain/tasks/pocket-voxel'
  import type { Task } from '@/types/models'
  import { fetchProtectedFileText } from '@/utils/protected-file-access'

  const props = defineProps<{ task: Task }>()
  const { t } = useI18n()

  const voxelGrid = ref<PocketVoxelGrid | null>(null)

  function fileDownloadUrl(file: { id?: string | number; url?: string }): string {
    return file.url || `/api/v1/files/${file.id}/download`
  }

  const receptorEntry = computed<VisualizationSceneEntry | null>(() => {
    const snapshot = (props.task.input_snapshots ?? []).find(item => {
      const role = String(item.inputRole || '').toLowerCase()
      return (role.includes('protein') || role.includes('receptor')) && Boolean(item.fileId || item.detail?.derived_from_file)
    })
    if (!snapshot) {
      return null
    }

    const fileId = snapshot.fileId || String(snapshot.detail?.derived_from_file || '')
    if (!fileId) {
      return null
    }

    return {
      key: 'pocket-receptor',
      url: `/api/v1/files/${fileId}/download`,
      label: String(snapshot.detail?.filename || t('tasks.resultPage.legendProtein')),
      source: 'input',
      role: 'receptor',
      format: 'pdb',
      extension: '.pdb',
    }
  })

  const pocketResiduesFile = computed(() =>
    (props.task.output_files ?? []).find(file => String(file.filename || '').toLowerCase() === 'protein_pocket_residues.pdb')
  )

  const pocketVoxelFile = computed(() =>
    (props.task.output_files ?? []).find(file => /^pocket\d+\.pdb$/i.test(String(file.filename || '')))
  )

  const pocketResiduesEntry = computed<VisualizationSceneEntry | null>(() => {
    const file = pocketResiduesFile.value
    if (!file) {
      return null
    }

    return {
      key: 'pocket-residues',
      url: fileDownloadUrl(file),
      label: String(file.filename || 'protein_pocket_residues.pdb'),
      source: 'output',
      role: 'pocket',
      format: 'pdb',
      extension: '.pdb',
    }
  })

  const scene = computed<VisualizationScene | null>(() => {
    const receptor = receptorEntry.value
    const residues = pocketResiduesEntry.value
    const entries: VisualizationSceneEntry[] = []

    if (receptor) {
      entries.push(receptor)
    }
    if (residues && receptor) {
      entries.push(residues)
    }
    if (!receptor && residues) {
      entries.push({ ...residues, key: 'pocket-only', role: 'receptor' })
    }

    if (!entries.length) {
      return null
    }

    return {
      entries,
      inputEntries: receptor ? [receptor] : [],
      outputEntries: residues ? [residues] : [],
      supportedOutputFiles: residues ? [residues] : [],
      unsupportedOutputFiles: [],
      hasRenderableOutput: true,
      selectedOutputKey: residues?.key ?? null,
    }
  })

  watch(
    pocketVoxelFile,
    async file => {
      if (!file) {
        voxelGrid.value = null
        return
      }

      try {
        const text = await fetchProtectedFileText(fileDownloadUrl(file))
        voxelGrid.value = { boxes: parsePocketVoxelBoxes(text, 0.9), color: 0x22d3ee, radius: 0.08 }
      } catch {
        voxelGrid.value = null
      }
    },
    { immediate: true },
  )
</script>

<style scoped lang="less">
  .pocket-complex {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
    margin-bottom: @spacing-lg;

    &__header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: @spacing-md;

      h4 {
        margin: 0 0 4px;
        font-size: 16px;
        font-weight: 600;
      }

      p {
        margin: 0;
        color: @text-secondary;
        line-height: 1.6;
      }
    }

    &__legend {
      display: flex;
      flex-wrap: wrap;
      gap: @spacing-sm;
    }

    &__legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 2px 10px;
      border: 1px solid @border-color;
      border-radius: 999px;
      color: @text-secondary;
      font-size: 12px;

      &::before {
        content: '';
        width: 8px;
        height: 8px;
        border-radius: 2px;
        background: @text-secondary;
      }

      &--protein::before {
        background: @accent-color;
      }

      &--pocket::before {
        background: @warning-color;
      }

      &--voxel::before {
        background: @info-color;
      }
    }
  }
</style>
