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

    <!-- 等体素格也解析完再挂 viewer：MoleculeViewer 对 entries/voxelGrid 都是 deep watch，
         先挂载再补体素会把整份结构重新下载、重渲染一次（用户看到的就是加载两遍）。 -->
    <MoleculeViewer
      v-if="scene && voxelReady"
      :scene="scene"
      :voxel-grid="voxelGrid"
    />
    <a-spin v-else-if="scene" size="small" :tip="t('tasks.resultPage.pocketComplexLoading')" />
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
  import type { Task, TaskInputSnapshot } from '@/types/models'
  import { fetchProtectedFileText } from '@/utils/protected-file-access'
  
  const props = defineProps<{ task: Task }>()
  const { t } = useI18n()

  const voxelGrid = ref<PocketVoxelGrid | null>(null)
  /** 体素格解析是否已经有结论（成功或失败都算）：没有它就先不挂 viewer，避免二次重载。 */
  const voxelReady = ref(false)

  function fileDownloadUrl(file: { id?: string | number; url?: string }): string {
    return file.url || `/api/v1/files/${file.id}/download`
  }

  function detailText(value: unknown): string {
    return typeof value === 'string' ? value.trim() : ''
  }

  /**
   * 把输入快照还原成「能下载的 URL」。
   *
   * 快照有三种形态：用户上传的文件（`fileId` 有值）、平台物化出的产物版本
   * （`artifact:<versionId>`）、领域结构（`file:<id>`）。早期写入的快照只有 URN、
   * 没有 `file_id`，所以这里必须能从 URN 反推；否则受体结构取不到，结果页只能
   * 退化成「只画口袋残基」——用户看到的现象就是「完整蛋白不见了」。
   */
  function snapshotFileUrl(snapshot: TaskInputSnapshot): string {
    const fileId =
      detailText(snapshot.fileId) ||
      detailText(snapshot.detail?.file_id) ||
      detailText(snapshot.detail?.derived_from_file)
    if (fileId) {
      return `/api/v1/files/${fileId}/download`
    }
    const urn = detailText(snapshot.urn)
    if (urn.startsWith('file:')) {
      const id = urn.slice('file:'.length)
      return id ? `/api/v1/files/${id}/download` : ''
    }
    if (urn.startsWith('artifact:')) {
      const id = urn.slice('artifact:'.length)
      return id ? `/api/v1/artifacts/versions/${id}/download` : ''
    }
    return ''
  }

  const STRUCTURE_EXTENSIONS = ['.pdb', '.ent', '.cif', '.mmcif']

  function looksLikeStructureName(label: string): boolean {
    const lower = label.trim().toLowerCase()
    return STRUCTURE_EXTENSIONS.some(ext => lower.endsWith(ext))
  }

  /**
   * 受体来源：直接用服务端解析好的 `fileId`（写入侧按 `is_primary → sort_order → role`
   * 挑主文件，读时还会纠正历史快照），**不在这里逐个下载探内容**——那会把服务端的
   * 排序缺陷变成客户端的额外流量与首屏延迟，几百 KB 的 PDB 每多试一条就多一次往返。
   *
   * 这里只做零成本筛选：同一条任务的受体快照可能不止一条（物化版本 + 领域结构），
   * 优先取文件名像坐标文件的那条；都不像就按顺序取第一条仍然有下载地址的。
   */
  const receptorEntry = computed<VisualizationSceneEntry | null>(() => {
    const snapshots = props.task.input_snapshots ?? []
    const candidates = snapshots
      .filter((snapshot) => {
        const role = String(snapshot.inputRole || '').toLowerCase()
        return role.includes('protein') || role.includes('receptor')
      })
      .map((snapshot) => ({
        url: snapshotFileUrl(snapshot),
        label: String(snapshot.detail?.filename || ''),
      }))
      .filter((candidate) => candidate.url)
    if (!candidates.length) {
      return null
    }
    const preferred = candidates.find((candidate) => looksLikeStructureName(candidate.label))
    const chosen = preferred ?? candidates[0]
    if (!chosen) {
      return null
    }

    return {
      key: 'pocket-receptor',
      url: chosen.url,
      label: chosen.label || t('tasks.resultPage.legendProtein'),
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
      voxelReady.value = false
      if (!file) {
        voxelGrid.value = null
        voxelReady.value = true
        return
      }

      try {
        const text = await fetchProtectedFileText(fileDownloadUrl(file))
        voxelGrid.value = { boxes: parsePocketVoxelBoxes(text, 0.9), color: 0x22d3ee, radius: 0.08 }
      } catch {
        voxelGrid.value = null
      } finally {
        voxelReady.value = true
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
