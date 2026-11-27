<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import MoleculeViewer from '@/components/tasks/MoleculeViewer.vue'
import AppDescriptionList from '@/components/common/AppDescriptionList.vue'
import type { DescriptionSection } from '@/components/common/AppDescriptionList.vue'
import { getResult } from '@/api/results'
import { getTaskDetail } from '@/api/tasks'
import { fetchProtectedFileText } from '@/utils/protected-file-access'
import { splitSdfRecords } from '@/domain/tasks/sdf-result'
import type { ProjectResultDetail, ResultOutputArtifact } from '@/types/compounds'
import type { Task } from '@/types/models'
import type { PoseInteraction, PoseMetadata, PosesMetadata } from '@/types/screening'
import type { VisualizationScene, VisualizationSceneEntry } from '@/domain/tasks'
import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'
import { findUniquePoseByTitle, getCachedDockingTask, parseResidueFocus, resolveDockingPose, setCachedDockingTask, sortDockingPoseCatalog } from './docking-poses'

interface ResidueFocusTarget {
  chain?: string
  authSeqId: number
  insertionCode?: string
}

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const loading = ref(true)
const errorMessage = ref('')
const poseMeta = ref<PoseMetadata | null>(null)
const receptorUrl = ref('')
const receptorFormatRef = ref<{ format: VisualizationSceneEntry['format']; extension: string }>({ format: 'pdb', extension: '.pdb' })
const receptorUnavailable = ref(false)
const poseUrl = ref('')
const sdfRecordIndex = ref<number | null>(null)
const catalog = ref<ReturnType<typeof sortDockingPoseCatalog>>([])
const activeFocusResidue = ref<ResidueFocusTarget | null>(null)
const taskId = computed(() => (typeof route.query.task_id === 'string' ? route.query.task_id : ''))
const poseId = computed(() => String(route.params.id ?? ''))
const poseRank = computed(() => poseMeta.value?.rank ?? 0)
const catalogIndex = computed(() => catalog.value.findIndex(item => item.pose.pose_id === poseMeta.value?.pose_id))
const LIGAND_STRUCTURE_STANDARD = 'ligand_structure@1'
let loadSeq = 0
let loadedTaskId = ''
let taskSdfBlobUrl = ''
let taskReceptorBlobUrl = ''

function revokeTaskBlobs(): void {
  if (taskSdfBlobUrl) {
    URL.revokeObjectURL(taskSdfBlobUrl)
    taskSdfBlobUrl = ''
  }
  if (taskReceptorBlobUrl) {
    URL.revokeObjectURL(taskReceptorBlobUrl)
    taskReceptorBlobUrl = ''
  }
}

function findLigandStructureArtifact(detail: ProjectResultDetail): ResultOutputArtifact | null {
  return detail.outputs.find(
    output =>
      output.standard_type === LIGAND_STRUCTURE_STANDARD ||
      output.artifact_type === 'ligand_structure' ||
      (output.semantic_type ?? '').startsWith('ligand_structure'),
  ) ?? null
}

function pickReceptorUrl(task: Task): string {
  const files = task.input_files ?? []
  const explicit = files.filter(
    file => /^(?:protein|receptor)(?:$|[_-])/i.test(file.relative_path ?? '') && typeof file.url === 'string',
  )
  if (explicit.length === 1) return explicit[0]!.url!
  const proteinExts = files.filter(
    file =>
      /\.(pdb|cif|mmcif|ent)$/i.test(file.filename ?? file.original_name ?? '') &&
      !/ligand/i.test(file.relative_path ?? file.filename ?? '') &&
      typeof file.url === 'string',
  )
  return proteinExts.length === 1 ? proteinExts[0]!.url! : ''
}

function inferFormat(task: Task | null, url: string): { format: VisualizationSceneEntry['format']; extension: string } {
  const matched = (task?.input_files ?? []).find(file => file.url === url)
  const name = (matched?.filename ?? matched?.original_name ?? url.split(/[?#]/, 1)[0] ?? '').toLowerCase()
  if (/\.mmcif$/.test(name) || /\.cif$/.test(name)) return { format: 'mmcif', extension: '.cif' }
  if (/\.pdbqt$/.test(name)) return { format: 'pdbqt', extension: '.pdbqt' }
  return { format: 'pdb', extension: '.pdb' }
}

const taskDetailRef = ref<Task | null>(null)

const scene = computed<VisualizationScene | null>(() => {
  if (!poseUrl.value || sdfRecordIndex.value === null || sdfRecordIndex.value < 0) return null
  const ligandEntry: VisualizationSceneEntry = {
    key: 'pose',
    url: poseUrl.value,
    label: poseMeta.value?.pose_id || poseId.value || `pose-${poseRank.value}`,
    source: 'output',
    role: 'ligand',
    format: 'sdf',
    extension: '.sdf',
    sdfRecordIndex: sdfRecordIndex.value,
  }
  const entries: VisualizationSceneEntry[] = []
  const inputEntries: VisualizationSceneEntry[] = []
  if (receptorUrl.value) {
    const receptorEntry: VisualizationSceneEntry = {
      key: 'receptor',
      url: receptorUrl.value,
      label: t('screening.detail.viewer'),
      source: 'input',
      role: 'receptor',
      ...receptorFormatRef.value,
    }
    entries.push(receptorEntry)
    inputEntries.push(receptorEntry)
  }
  entries.push(ligandEntry)
  return {
    entries,
    inputEntries,
    outputEntries: [ligandEntry],
    supportedOutputFiles: [ligandEntry],
    unsupportedOutputFiles: [],
    hasRenderableOutput: true,
    selectedOutputKey: 'pose',
  }
})

interface InteractionGroup {
  type: string
  label: string
  items: PoseInteraction[]
}

function groupLabel(type: string): string {
  const lower = type.toLowerCase()
  if (lower.includes('hydrogen') || lower.includes('hbond') || lower.includes('h-bond')) return t('screening.detail.groupHydrogenBond')
  if (lower.includes('hydrophobic')) return t('screening.detail.groupHydrophobic')
  if (lower.includes('ionic') || lower.includes('salt')) return t('screening.detail.groupIonic')
  if (lower.includes('pi') || lower.includes('stack')) return t('screening.detail.groupPiStacking')
  return t('screening.detail.groupOther')
}

const interactionGroups = computed<InteractionGroup[]>(() => {
  const groups = new Map<string, PoseInteraction[]>()
  for (const item of poseMeta.value?.interactions ?? []) {
    groups.set(item.type || 'other', [...(groups.get(item.type || 'other') ?? []), item])
  }
  return Array.from(groups.entries()).map(([type, items]) => ({
    type,
    label: groupLabel(type),
    items: [...items].sort((a, b) => a.distance - b.distance),
  }))
})

const interactionColumns = computed(() => [
  { title: t('screening.detail.type'), dataIndex: 'type', key: 'type' },
  { title: t('screening.detail.residue'), dataIndex: 'residue', key: 'residue' },
  { title: t('screening.detail.chain'), dataIndex: 'chain', key: 'chain' },
  { title: t('screening.detail.distance'), dataIndex: 'distance', key: 'distance', align: 'right' },
])

function handleInteractionFocus(record: PoseInteraction): void {
  const parsed = parseResidueFocus(record.residue ?? '', record.chain)
  if (!parsed) {
    message.warning(t('screening.detail.focusNotFound'))
    return
  }
  activeFocusResidue.value = parsed
}

function handleResidueFocusResult(status: 'focused' | 'not-found' | 'ambiguous'): void {
  if (status === 'not-found') message.warning(t('screening.detail.focusNotFound'))
  else if (status === 'ambiguous') message.warning(t('screening.detail.focusAmbiguous'))
}

function applyPoseFromCatalog(): void {
  activeFocusResidue.value = null
  const resolved = resolveDockingPose(catalog.value, poseId.value)
  if (!resolved) {
    poseMeta.value = null
    sdfRecordIndex.value = null
    errorMessage.value = t('screening.detail.poseMissing')
    return
  }
  errorMessage.value = ''
  poseMeta.value = resolved.pose
  sdfRecordIndex.value = resolved.recordIndex
}

function isMissingResourceError(cause: unknown): boolean {
  const text = cause instanceof Error ? cause.message : String(cause)
  return /\b404\b|not found/i.test(text)
}

async function buildVinaFallbackCatalog(detail: ProjectResultDetail, seq: number): Promise<{ poses: ReturnType<typeof sortDockingPoseCatalog>; sdfText: string } | null> {
  const tableArtifact = detail.outputs.find(o => o.standard_type === 'molecule_table@1' || o.semantic_type === 'molecule_table')
  const sdfArtifact = detail.outputs.find(o => o.standard_type === LIGAND_STRUCTURE_STANDARD || o.semantic_type === 'ligand_structure') ?? tableArtifact
  if (!tableArtifact?.version_id || !sdfArtifact?.version_id) return null
  const csvUrl = `/api/v1/artifacts/${tableArtifact.id}/versions/${tableArtifact.version_id}/files/table_file/download`
  const sdfDownloadUrl = `/api/v1/artifacts/${sdfArtifact.id}/versions/${sdfArtifact.version_id}/files/structure_file/download`
  const [csvText, sdfText] = await Promise.all([fetchProtectedFileText(csvUrl), fetchProtectedFileText(sdfDownloadUrl)])
  if (seq !== loadSeq) return null
  const titles = splitSdfRecords(sdfText).map(rec => (rec.split(/\r?\n/, 1)[0] ?? '').trim())
  const lines = csvText.trim().split(/\r?\n/)
  const headers = (lines.shift() ?? '').split(',').map(h => h.trim().toLowerCase())
  const idIdx = headers.findIndex(h => h === 'molecule_id' || h === 'pose_id')
  const rankIdx = headers.indexOf('rank')
  const scoreIdx = headers.indexOf('docking_score')
  const rmsdLbIdx = headers.indexOf('rmsd_lb')
  const rmsdUbIdx = headers.indexOf('rmsd_ub')
  const smilesIdx = headers.indexOf('smiles')
  const entries: Array<{ pose: PoseMetadata; recordIndex: number; sourceOrder: number }> = []
  lines.forEach((line, sourceOrder) => {
    const cols = line.split(',')
    const molId = idIdx >= 0 ? (cols[idIdx] ?? '').trim() : `pose-${sourceOrder + 1}`
    const rank = rankIdx >= 0 && Number(cols[rankIdx]) > 0 ? Number(cols[rankIdx]) : sourceOrder + 1
    const matchedIdx = findUniquePoseByTitle(titles, molId)
    entries.push({
      pose: {
        pose_id: molId || `pose-${rank}`,
        rank,
        // 表格里没有该列时记为 NaN，展示层统一落成「未提供」，不再伪造 0。
        docking_score: scoreIdx >= 0 ? parseMetricCell(cols[scoreIdx]) : Number.NaN,
        rmsd_lb: rmsdLbIdx >= 0 ? parseMetricCell(cols[rmsdLbIdx]) : Number.NaN,
        rmsd_ub: rmsdUbIdx >= 0 ? parseMetricCell(cols[rmsdUbIdx]) : Number.NaN,
        ligand_smiles: smilesIdx >= 0 ? cols[smilesIdx]?.trim() : undefined,
        interactions: [],
      },
      recordIndex: matchedIdx ?? -1,
      sourceOrder,
    })
  })
  return { poses: entries.sort((a, b) => a.pose.rank - b.pose.rank || a.sourceOrder - b.sourceOrder), sdfText }
}

async function load(): Promise<void> {
  const currentTask = taskId.value
  const seq = ++loadSeq
  activeFocusResidue.value = null
  if (!currentTask) {
    errorMessage.value = t('screening.detail.needTask')
    loading.value = false
    return
  }
  if (loadedTaskId === currentTask && catalog.value.length > 0 && poseUrl.value) {
    applyPoseFromCatalog()
    loading.value = false
    return
  }
  const cached = getCachedDockingTask(currentTask)
  if (cached) {
    revokeTaskBlobs()
    catalog.value = cached.catalog
    taskSdfBlobUrl = URL.createObjectURL(new Blob([cached.sdfText], { type: 'chemical/x-mdl-sdfile' }))
    poseUrl.value = taskSdfBlobUrl
    if (cached.receptorText !== null && cached.receptorFormat) {
      taskReceptorBlobUrl = URL.createObjectURL(new Blob([cached.receptorText], { type: 'text/plain' }))
      receptorFormatRef.value = cached.receptorFormat
      receptorUrl.value = taskReceptorBlobUrl
      receptorUnavailable.value = false
    } else {
      receptorUrl.value = ''
      receptorUnavailable.value = cached.receptorUnavailable
    }
    loadedTaskId = currentTask
    applyPoseFromCatalog()
    loading.value = false
    return
  }
  loading.value = true
  errorMessage.value = ''
  catalog.value = []
  poseMeta.value = null
  poseUrl.value = ''
  receptorUrl.value = ''
  receptorUnavailable.value = false
  revokeTaskBlobs()
  try {
    const detailResponse = await getResult(currentTask)
    if (seq !== loadSeq) return
    const detail = detailResponse.data as ProjectResultDetail
    const artifact = findLigandStructureArtifact(detail)
    let resolvedSdfText = ''
    if (artifact && artifact.version_id) {
      const base = `/api/v1/artifacts/${artifact.id}/versions/${artifact.version_id}/files`
      try {
        const [metadataText, sdfText] = await Promise.all([
          fetchProtectedFileText(`${base}/metadata_json/download`),
          fetchProtectedFileText(`${base}/structure_3d_sdf/download`),
        ])
        if (seq !== loadSeq) return
        resolvedSdfText = sdfText
        const metadata = JSON.parse(metadataText) as PosesMetadata
        const rawPoses = metadata.poses ?? []
        const sdfRecords = splitSdfRecords(sdfText)
        const sdfTitles = sdfRecords.map(rec => (rec.split(/\r?\n/, 1)[0] ?? '').trim())
        const canPairOrdinally = rawPoses.length === sdfRecords.length
        catalog.value = rawPoses
          .map((pose, sourceOrder) => {
            const matched = findUniquePoseByTitle(sdfTitles, pose.pose_id)
            const recordIndex = matched !== null ? matched : canPairOrdinally ? sourceOrder : -1
            return { pose, recordIndex, sourceOrder }
          })
          .sort((a, b) => a.pose.rank - b.pose.rank || a.sourceOrder - b.sourceOrder)
        taskSdfBlobUrl = URL.createObjectURL(new Blob([sdfText], { type: 'chemical/x-mdl-sdfile' }))
        poseUrl.value = taskSdfBlobUrl
      } catch (metaCause) {
        if (!isMissingResourceError(metaCause)) throw metaCause
        const fallback = await buildVinaFallbackCatalog(detail, seq)
        if (!fallback) throw metaCause
        resolvedSdfText = fallback.sdfText
        catalog.value = fallback.poses
        taskSdfBlobUrl = URL.createObjectURL(new Blob([fallback.sdfText], { type: 'chemical/x-mdl-sdfile' }))
        poseUrl.value = taskSdfBlobUrl
      }
    } else {
      const fallback = await buildVinaFallbackCatalog(detail, seq)
      if (!fallback) throw new Error(t('screening.detail.poseMissing'))
      resolvedSdfText = fallback.sdfText
      catalog.value = fallback.poses
      taskSdfBlobUrl = URL.createObjectURL(new Blob([fallback.sdfText], { type: 'chemical/x-mdl-sdfile' }))
      poseUrl.value = taskSdfBlobUrl
    }
    loadedTaskId = currentTask
    applyPoseFromCatalog()
    let receptorText: string | null = null
    let receptorFmt: { format: 'pdb' | 'mmcif' | 'pdbqt'; extension: string } | null = null
    try {
      const taskData = (await getTaskDetail(currentTask)).data
      if (seq !== loadSeq) return
      taskDetailRef.value = taskData
      const rawReceptorUrl = pickReceptorUrl(taskData)
      if (rawReceptorUrl) {
        const inferred = inferFormat(taskData, rawReceptorUrl)
        if (inferred.format === 'pdb' || inferred.format === 'mmcif' || inferred.format === 'pdbqt') {
          receptorFmt = { format: inferred.format, extension: inferred.extension }
          receptorText = await fetchProtectedFileText(rawReceptorUrl)
          if (seq !== loadSeq) return
          receptorFormatRef.value = receptorFmt
          taskReceptorBlobUrl = URL.createObjectURL(new Blob([receptorText], { type: 'text/plain' }))
          receptorUrl.value = taskReceptorBlobUrl
          receptorUnavailable.value = false
        } else {
          receptorUrl.value = rawReceptorUrl
          receptorFormatRef.value = inferred
          receptorUnavailable.value = false
        }
      } else {
        receptorUnavailable.value = true
      }
    } catch {
      if (seq === loadSeq) {
        receptorUrl.value = ''
        receptorUnavailable.value = true
        receptorText = null
      }
    }
    if (seq === loadSeq) {
      setCachedDockingTask({
        taskId: currentTask,
        catalog: catalog.value,
        sdfText: resolvedSdfText,
        receptorText,
        receptorFormat: receptorFmt,
        receptorUnavailable: receptorUnavailable.value,
      })
    }
  } catch (cause) {
    if (seq === loadSeq) {
      errorMessage.value = cause instanceof Error ? cause.message : t('screening.detail.loadFailed')
    }
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function stepPose(delta: -1 | 1): void {
  const target = catalog.value[catalogIndex.value + delta]
  if (!target || !taskId.value) return
  void router.push({
    name: 'DockingResultDetail',
    params: { id: target.pose.pose_id },
    query: { ...route.query, task_id: taskId.value },
  })
}

onMounted(() => { void load() })
watch(taskId, () => {
  loadedTaskId = ''
  void load()
})
watch(poseId, () => {
  if (loadedTaskId === taskId.value && catalog.value.length > 0) applyPoseFromCatalog()
})
onUnmounted(() => {
  loadSeq += 1
  revokeTaskBlobs()
})

/**
 * 指标展示：空值 / 非有限数统一显示「未提供」，但合法的 0 必须保留。
 * 后端元数据可能把缺失指标序列化为 null，前端类型又声明为 number，运行时两者都会出现。
 */
function formatMetric(value: unknown): string {
  if (value === null || value === undefined) return t('screening.detail.notProvided')
  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : t('screening.detail.notProvided')
  }
  const text = String(value).trim()
  return text === '' ? t('screening.detail.notProvided') : text
}

/** CSV 兜底表里的数值列：空串/非法值视为缺失，而不是误报成 0。 */
function parseMetricCell(value: string | undefined): number {
  const text = (value ?? '').trim()
  if (!text) return Number.NaN
  const parsed = Number(text)
  return Number.isFinite(parsed) ? parsed : Number.NaN
}

const poseSections = computed<DescriptionSection[]>(() => {
  const pose = poseMeta.value
  if (!pose) return []
  const fields: DescriptionSection['fields'] = [
    { key: 'rank', label: t('screening.detail.rank'), value: String(pose.rank) },
    { key: 'score', label: t('screening.detail.score'), value: formatMetric(pose.docking_score), hint: t('screening.detail.hints.score') },
    { key: 'rmsdLb', label: t('screening.detail.rmsdLb'), value: formatMetric(pose.rmsd_lb), hint: t('screening.detail.hints.rmsd') },
    { key: 'rmsdUb', label: t('screening.detail.rmsdUb'), value: formatMetric(pose.rmsd_ub), hint: t('screening.detail.hints.rmsd') },
  ]
  if (pose.ligand_smiles) {
    fields.push({ key: 'ligandSmiles', label: t('screening.detail.ligandSmiles'), value: pose.ligand_smiles, mono: true, span: 4 })
  }
  return [{ key: 'pose', fields }]
})
</script>

<template>
  <main class="docking-detail" data-testid="docking-detail-page">
    <AppPageHeader :title="t('screening.detail.title')" :subtitle="t('screening.detail.subtitle')">
      <template #actions>
        <a-space>
          <router-link v-if="taskId" :to="`/tasks/${taskId}`">
            <a-button data-testid="docking-detail-task-detail">{{ t('tasks.taskWorkspace.detail') }}</a-button>
          </router-link>
          <router-link :to="`/tasks/${taskId}/screening`">
            <a-button data-testid="docking-detail-back">{{ t('screening.detail.back') }}</a-button>
          </router-link>
        </a-space>
      </template>
    </AppPageHeader>

    <a-alert v-if="errorMessage" type="error" show-icon data-testid="docking-detail-error" :message="errorMessage" />
    <div v-if="loading" data-testid="docking-detail-loading"><a-spin /> {{ t('screening.detail.loading') }}</div>

    <template v-else-if="!errorMessage && poseMeta">
      <a-card :title="poseMeta.pose_id" data-testid="docking-detail-score">
        <AppDescriptionList :sections="poseSections" :columns="4" />
      </a-card>

      <a-space v-if="catalog.length > 1" class="docking-detail__stepper">
        <a-button data-testid="docking-detail-previous" :disabled="catalogIndex <= 0" @click="stepPose(-1)">
          {{ t('screening.detail.previousPose') }}
        </a-button>
        <span>{{ catalogIndex + 1 }} / {{ catalog.length }}</span>
        <a-button data-testid="docking-detail-next" :disabled="catalogIndex < 0 || catalogIndex >= catalog.length - 1" @click="stepPose(1)">
          {{ t('screening.detail.nextPose') }}
        </a-button>
      </a-space>

      <a-alert
        v-if="receptorUnavailable"
        type="info"
        show-icon
        data-testid="docking-detail-receptor-warning"
        :message="t('screening.detail.receptorUnavailable')"
      />

      <a-card :title="t('screening.detail.viewer')">
        <div data-testid="docking-detail-viewer">
          <MoleculeViewer v-if="scene" :scene="scene" mode="docking" variant="full" :focus-residue="activeFocusResidue" :enable-nearby-residues="true" @residue-focus-result="handleResidueFocusResult" />
          <a-empty v-else :description="t('screening.detail.poseUnavailable')" data-testid="docking-detail-unavailable" />
        </div>
      </a-card>

      <a-card :title="t('screening.detail.interactions')" data-testid="docking-detail-interactions">
        <a-empty v-if="!interactionGroups.length" :description="t('screening.detail.interactionEmpty')" />
        <div v-else class="docking-detail__groups">
          <div v-for="group in interactionGroups" :key="group.type" class="docking-detail__group">
            <h4 class="docking-detail__group-title">{{ group.label }}</h4>
            <a-table
              :columns="interactionColumns"
              :data-source="group.items"
              :pagination="false"
              :row-key="(_record: PoseInteraction, index: number) => index"
              :custom-row="(record: PoseInteraction) => ({ style: 'cursor: pointer;', onClick: () => handleInteractionFocus(record) })"
              size="small"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'residue'">
                  <button
                    type="button"
                    class="docking-detail__residue-btn"
                    data-testid="docking-interaction-residue"
                    @click.stop="handleInteractionFocus(record as PoseInteraction)"
                  >
                    {{ (record as PoseInteraction).residue }}
                  </button>
                </template>
              </template>
            </a-table>
          </div>
        </div>
      </a-card>
    </template>
  </main>
  <ResultDisclaimer />
</template>

<style scoped lang="less">
.docking-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
}

.docking-detail__groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.docking-detail__group-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

/*
 * AppDescriptionList 的 hint 默认是固定的 rgba(0,0,0,.45)，暗色主题下几乎不可读。
 * 这里用主题变量覆盖成本页可读的灰阶，并改为独占一行，长文案有足够空间换行。
 */
:deep(.app-description-hint) {
  display: block;
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--theme-text-secondary, #64748b);
  white-space: normal;
}

.docking-detail__residue-btn {
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--ant-color-primary, #1677ff);
  font: inherit;
  cursor: pointer;
  text-decoration: underline;
}
</style>
