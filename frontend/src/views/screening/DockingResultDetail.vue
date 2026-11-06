<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import MoleculeViewer from '@/components/tasks/MoleculeViewer.vue'
import AppDescriptionList from '@/components/common/AppDescriptionList.vue'
import type { DescriptionSection } from '@/components/common/AppDescriptionList.vue'
import { getResult } from '@/api/results'
import { getTaskDetail } from '@/api/tasks'
import { fetchProtectedFileText } from '@/utils/protected-file-access'
import type { ProjectResultDetail, ResultOutputArtifact } from '@/types/compounds'
import type { Task } from '@/types/models'
import type { PoseInteraction, PoseMetadata, PosesMetadata } from '@/types/screening'
import type { VisualizationScene, VisualizationSceneEntry } from '@/domain/tasks'

const route = useRoute()
const { t } = useI18n()

const loading = ref(true)
const errorMessage = ref('')
const poseMeta = ref<PoseMetadata | null>(null)
const receptorUrl = ref('')
const poseUrl = ref('')
const sdfRecordIndex = ref(0)

const taskId = computed(() => {
  const raw = route.query.task_id
  return typeof raw === 'string' ? raw : ''
})
const poseId = computed(() => String(route.params.id ?? ''))
const poseRank = computed(() => poseMeta.value?.rank ?? 0)

const LIGAND_STRUCTURE_STANDARD = 'ligand_structure@1'

function findLigandStructureArtifact(detail: ProjectResultDetail): ResultOutputArtifact | null {
  const found = detail.outputs.find(
    output =>
      output.standard_type === LIGAND_STRUCTURE_STANDARD ||
      output.artifact_type === 'ligand_structure' ||
      (output.semantic_type ?? '').startsWith('ligand_structure')
  )
  return found ?? null
}

function pickReceptorUrl(task: Task): string {
  const files = task.input_files ?? []
  for (const file of files) {
    const name = (file.filename ?? file.original_name ?? '').toLowerCase()
    if (/[.](pdb|cif|mmcif|pdbqt)$/.test(name) && typeof file.url === 'string') {
      return file.url
    }
  }
  const withUrl = files.find(file => typeof file.url === 'string')
  return withUrl?.url ?? ''
}

function inferFormat(url: string): { format: VisualizationSceneEntry['format']; extension: string } {
  const lower = url.toLowerCase()
  if (lower.includes('.mmcif') || lower.includes('.cif')) {
    return { format: 'mmcif', extension: '.cif' }
  }
  if (lower.includes('.pdbqt')) {
    return { format: 'pdbqt', extension: '.pdbqt' }
  }
  if (lower.includes('.mol2')) {
    return { format: 'mol2', extension: '.mol2' }
  }
  if (lower.includes('.sdf')) {
    return { format: 'sdf', extension: '.sdf' }
  }
  return { format: 'pdb', extension: '.pdb' }
}

const scene = computed<VisualizationScene | null>(() => {
  if (!poseUrl.value) {
    return null
  }
  const ligandEntry: VisualizationSceneEntry = {
    key: 'pose',
    url: poseUrl.value,
    label: poseId.value || `pose-${poseRank.value}`,
    source: 'output',
    role: 'ligand',
    format: 'sdf',
    extension: '.sdf',
    sdfRecordIndex: sdfRecordIndex.value
  }
  const entries: VisualizationSceneEntry[] = []
  const inputEntries: VisualizationSceneEntry[] = []
  if (receptorUrl.value) {
    const receptorFormat = inferFormat(receptorUrl.value)
    const receptorEntry: VisualizationSceneEntry = {
      key: 'receptor',
      url: receptorUrl.value,
      label: t('screening.detail.viewer'),
      source: 'input',
      role: 'receptor',
      format: receptorFormat.format,
      extension: receptorFormat.extension
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
    selectedOutputKey: 'pose'
  }
})

interface InteractionGroup {
  type: string
  label: string
  items: PoseInteraction[]
}

function groupLabel(type: string): string {
  const lower = type.toLowerCase()
  if (lower.includes('hydrogen') || lower.includes('hbond') || lower.includes('h-bond')) {
    return t('screening.detail.groupHydrogenBond')
  }
  if (lower.includes('hydrophobic')) {
    return t('screening.detail.groupHydrophobic')
  }
  if (lower.includes('ionic') || lower.includes('salt')) {
    return t('screening.detail.groupIonic')
  }
  if (lower.includes('pi') || lower.includes('stack')) {
    return t('screening.detail.groupPiStacking')
  }
  return t('screening.detail.groupOther')
}

const interactionGroups = computed<InteractionGroup[]>(() => {
  const list = poseMeta.value?.interactions ?? []
  const groups = new Map<string, PoseInteraction[]>()
  for (const item of list) {
    const key = item.type || 'other'
    const bucket = groups.get(key)
    if (bucket) {
      bucket.push(item)
    } else {
      groups.set(key, [item])
    }
  }
  return Array.from(groups.entries()).map(([type, items]) => ({
    type,
    label: groupLabel(type),
    items: [...items].sort((left, right) => left.distance - right.distance)
  }))
})

const interactionColumns = computed(() => [
  { title: t('screening.detail.type'), dataIndex: 'type', key: 'type' },
  { title: t('screening.detail.residue'), dataIndex: 'residue', key: 'residue' },
  { title: t('screening.detail.chain'), dataIndex: 'chain', key: 'chain' },
  { title: t('screening.detail.distance'), dataIndex: 'distance', key: 'distance', align: 'right' }
])

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  if (!taskId.value) {
    errorMessage.value = t('screening.detail.needTask')
    loading.value = false
    return
  }
  try {
    const resultResponse = await getResult(taskId.value)
    const detail: ProjectResultDetail & { mock?: boolean } = resultResponse.data

    const artifact = findLigandStructureArtifact(detail)
    if (!artifact || !artifact.version_id) {
      throw new Error(t('screening.detail.poseMissing'))
    }
    const base = `/api/v1/artifacts/${artifact.id}/versions/${artifact.version_id}/files`
    const metadataText = await fetchProtectedFileText(`${base}/metadata_json/download`)
    const metadata = JSON.parse(metadataText) as PosesMetadata

    let meta = metadata.poses.find(item => item.pose_id === poseId.value)
    if (!meta) {
      const rankFromId = Number(poseId.value.replace(/^pose-/, ''))
      meta = metadata.poses.find(item => item.rank === rankFromId)
    }
    if (!meta) {
      throw new Error(t('screening.detail.poseMissing'))
    }
    poseMeta.value = meta
    sdfRecordIndex.value = Math.max(0, meta.rank - 1)
    poseUrl.value = `${base}/structure_3d_sdf/download`

    try {
      const taskResponse = await getTaskDetail(taskId.value)
      receptorUrl.value = pickReceptorUrl(taskResponse.data)
    } catch {
      receptorUrl.value = ''
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t('screening.detail.loadFailed')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

  const poseSections = computed<DescriptionSection[]>(() => {
    const pose = poseMeta.value
    if (!pose) {
      return []
    }
    const fields: DescriptionSection['fields'] = [
      { key: 'rank', label: t('screening.detail.rank'), value: String(pose.rank) },
      { key: 'score', label: t('screening.detail.score'), value: String(pose.docking_score), hint: t('screening.detail.hints.score') },
      { key: 'rmsdLb', label: t('screening.detail.rmsdLb'), value: String(pose.rmsd_lb), hint: t('screening.detail.hints.rmsd') },
      { key: 'rmsdUb', label: t('screening.detail.rmsdUb'), value: String(pose.rmsd_ub), hint: t('screening.detail.hints.rmsd') },
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

    <a-alert
      v-if="errorMessage"
      type="error"
      show-icon
      data-testid="docking-detail-error"
      :message="errorMessage"
    />

    <div v-if="loading" data-testid="docking-detail-loading">
      <a-spin /> {{ t('screening.detail.loading') }}
    </div>

    <template v-else-if="!errorMessage && poseMeta">
      <a-card :title="poseMeta.pose_id" data-testid="docking-detail-score">
        <AppDescriptionList :sections="poseSections" :columns="4" />
      </a-card>

      <a-card :title="t('screening.detail.viewer')">
        <div data-testid="docking-detail-viewer">
          <MoleculeViewer v-if="scene" :scene="scene" variant="full" />
          <a-empty v-else :description="t('screening.detail.noStructure')" />
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
              :row-key="(_record: Record<string, string>, index: number) => index"
              size="small"
            />
          </div>
        </div>
      </a-card>
    </template>
  </main>
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
</style>
