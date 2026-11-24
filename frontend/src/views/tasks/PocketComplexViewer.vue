<template>
  <section class="pocket-complex" data-testid="pocket-complex-viewer">
    <header class="pocket-complex__header">
      <div>
        <h4>{{ t('tasks.resultPage.pocketComplexTitle') }}</h4>
        <p>{{ t('tasks.resultPage.pocketComplexHint') }}</p>
      </div>
      <div class="pocket-complex__legend">
        <span v-if="receptorEntry" class="pocket-complex__legend-item pocket-complex__legend-item--protein">{{ t('tasks.resultPage.legendProtein') }}</span>
        <span v-if="pocketResiduesEntry" class="pocket-complex__legend-item pocket-complex__legend-item--pocket">{{ t('tasks.resultPage.legendPocket') }}</span>
        <span v-if="voxelGrid?.boxes.length" class="pocket-complex__legend-item pocket-complex__legend-item--voxel">{{ t('tasks.resultPage.legendVoxel') }}</span>
      </div>
    </header>
    <MoleculeViewer v-if="scene && voxelReady" :scene="scene" mode="protein" :voxel-grid="voxelGrid" :enable-nearby-residues="true" />
    <a-spin v-else-if="scene" size="small" :tip="t('tasks.resultPage.pocketComplexLoading')" />
    <a-alert v-else type="warning" show-icon :message="t('tasks.resultPage.proteinStructureMissing')" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import MoleculeViewer from '@/components/tasks/MoleculeViewer.vue'
import { detectVisualizationFormat } from '@/domain/tasks'
import type { VisualizationScene, VisualizationSceneEntry } from '@/domain/tasks'
import { parsePocketVoxelBoxes, type PocketVoxelGrid } from '@/domain/tasks/pocket-voxel'
import type { Task, TaskInputSnapshot } from '@/types/models'
import { fetchProtectedFileText } from '@/utils/protected-file-access'

const props = defineProps<{ task: Task; selectedPocketId?: string; selectedResIds?: number[] }>()
const { t } = useI18n()
const voxelGrid = ref<PocketVoxelGrid | null>(null)
const voxelReady = ref(false)
let voxelRequestSeq = 0
function fileDownloadUrl(file: { id?: string | number; url?: string }): string { return file.url || `/api/v1/files/${file.id}/download` }
function detailText(value: unknown): string { return typeof value === 'string' ? value.trim() : '' }
function snapshotFileUrl(snapshot: TaskInputSnapshot): string {
  const id = detailText(snapshot.fileId) || detailText(snapshot.detail?.file_id) || detailText(snapshot.detail?.derived_from_file)
  if (id) return `/api/v1/files/${id}/download`
  const urn = detailText(snapshot.urn)
  if (urn.startsWith('file:')) return `/api/v1/files/${urn.slice(5)}/download`
  if (urn.startsWith('artifact:')) return `/api/v1/artifacts/versions/${urn.slice(9)}/download`
  return ''
}
function formatEntry(url: string, label: string, key: string, role: VisualizationSceneEntry['role'], source: VisualizationSceneEntry['source']): VisualizationSceneEntry {
  const reference = { filename: label || url }
  const format = detectVisualizationFormat(reference)
  return { key, url, label, source, role, format: format ?? 'pdb', extension: label.match(/\.[^.]+$/)?.[0] ?? '.pdb' }
}
const receptorEntry = computed<VisualizationSceneEntry | null>(() => {
  const candidates = (props.task.input_snapshots ?? []).filter(snapshot => /protein|receptor/i.test(snapshot.inputRole ?? '')).map(snapshot => ({ url: snapshotFileUrl(snapshot), label: detailText(snapshot.detail?.filename) })).filter(item => item.url)
  if (!candidates.length) return null
  const chosen = candidates.find(item => detectVisualizationFormat({ filename: item.label })) ?? (candidates.length === 1 ? candidates[0] : undefined)
  return chosen ? formatEntry(chosen.url, chosen.label || t('tasks.resultPage.legendProtein'), 'pocket-receptor', 'receptor', 'input') : null
})
const pocketResiduesEntry = computed<VisualizationSceneEntry | null>(() => {
  const file = (props.task.output_files ?? []).find(item => String(item.filename || '').toLowerCase() === 'protein_pocket_residues.pdb')
  return file ? formatEntry(fileDownloadUrl(file), t('tasks.resultPage.pocketResiduesOverlay'), 'pocket-residues', 'pocket', 'output') : null
})
const pocketVoxelFile = computed(() => (props.task.output_files ?? []).find(file => new RegExp(`^${props.selectedPocketId || 'pocket'}\\d*\\.pdb$`, 'i').test(String(file.filename || ''))))
const scene = computed<VisualizationScene | null>(() => {
  const entries: VisualizationSceneEntry[] = []
  if (receptorEntry.value) entries.push(receptorEntry.value)
  if (pocketResiduesEntry.value) entries.push(pocketResiduesEntry.value)
  if (!entries.length) return null
  return { entries, inputEntries: receptorEntry.value ? [receptorEntry.value] : [], outputEntries: pocketResiduesEntry.value ? [pocketResiduesEntry.value] : [], supportedOutputFiles: pocketResiduesEntry.value ? [pocketResiduesEntry.value] : [], unsupportedOutputFiles: [], hasRenderableOutput: true, selectedOutputKey: pocketResiduesEntry.value?.key ?? null }
})
watch(pocketVoxelFile, async file => {
  const seq = ++voxelRequestSeq
  voxelReady.value = false
  voxelGrid.value = null
  if (!file) { voxelReady.value = true; return }
  try {
    const text = await fetchProtectedFileText(fileDownloadUrl(file))
    if (seq === voxelRequestSeq) voxelGrid.value = { boxes: parsePocketVoxelBoxes(text, 0.9), color: 0x22d3ee, radius: 0.08 }
  } catch { if (seq === voxelRequestSeq) voxelGrid.value = null }
  finally { if (seq === voxelRequestSeq) voxelReady.value = true }
}, { immediate: true })
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
        /* 与 MoleculeViewer 里受体卡通渲染色一致（0x9ca3af），图例颜色必须等于看到的颜色 */
        background: #9ca3af;
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
