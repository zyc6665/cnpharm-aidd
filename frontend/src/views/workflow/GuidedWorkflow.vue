<template>
  <div class="guided-workflow">
    <a-steps :current="current" size="small" class="guided-steps" @change="onStepChange">
      <a-step v-for="stage in stages" :key="stage.key" :title="stage.title" />
    </a-steps>

    <div class="guided-body">
      <div class="stage-head">
        <div>
          <h3 class="stage-title">{{ currentStage.title }}</h3>
          <p class="stage-desc">{{ currentStage.desc }}</p>
        </div>
        <a-tag v-if="currentStage.hint" color="blue">{{ currentStage.hint }}</a-tag>
      </div>

      <a-spin :spinning="loading">
        <!-- 1. 结构预测（就地） -->
        <div v-if="currentStage.key === 'structure'" class="stage-panel">
          <a-descriptions :column="3" size="small" bordered>
            <a-descriptions-item label="靶点">{{ target?.name || '未登记' }}</a-descriptions-item>
            <a-descriptions-item label="蛋白">{{ protein?.name || '未登记' }}</a-descriptions-item>
            <a-descriptions-item label="结构数">{{ structureCount }}</a-descriptions-item>
          </a-descriptions>
          <StructurePredictForm
            v-if="proteinId"
            :protein-id="proteinId"
            @submitted="snapshotStructures"
            @completed="handleStructureCompleted"
            @error="handleStageError"
          />
          <p v-else class="stage-note">该靶点下还没有蛋白，请先在「靶点与结构」添加蛋白序列。</p>
          <div class="stage-actions">
            <span class="stage-note">就地提交 Boltz-2 结构预测，完成后自动进入口袋预测。</span>
            <a-button type="link" :disabled="!structureId" @click="goStructureDetail">去结构详情</a-button>
          </div>
        </div>

        <!-- 2. 口袋识别（就地） -->
        <div v-else-if="currentStage.key === 'pocket'" class="stage-panel">
          <a-descriptions :column="3" size="small" bordered>
            <a-descriptions-item label="可用结构">{{ structureCount }}</a-descriptions-item>
            <a-descriptions-item label="已识别口袋">{{ pocketCount }}</a-descriptions-item>
            <a-descriptions-item label="口袋工具">LVpocket</a-descriptions-item>
          </a-descriptions>
          <PocketPredictPanel
            v-if="structureId"
            :structure-id="structureId"
            @predicted="handlePocketPredicted"
            @selected="handlePocketSelected"
          />
          <p v-else class="stage-note">还没有可用结构，请先完成结构预测。</p>
          <div class="stage-actions">
            <span class="stage-note">就地预测口袋并「选定」一个作为设计起点，完成后自动进入分子生成。</span>
            <a-button type="link" :disabled="!structureId" @click="goPockets">去口袋页批量管理</a-button>
          </div>
        </div>

        <!-- 3. 分子生成 -->
        <div v-else-if="currentStage.key === 'molecule'" class="stage-panel stage-panel--embed">
          <MoleculeGeneration :initial-project-id="projectId" />
        </div>

        <!-- 4. 多肽设计 -->
        <div v-else-if="currentStage.key === 'peptide'" class="stage-panel stage-panel--embed">
          <PeptideDesign :initial-project-id="projectId" />
        </div>

        <!-- 5. 亲和力预测 -->
        <div v-else-if="currentStage.key === 'affinity'" class="stage-panel">
          <a-descriptions :column="3" size="small" bordered>
            <a-descriptions-item label="靶点">{{ target?.name || '未登记' }}</a-descriptions-item>
            <a-descriptions-item label="候选物">{{ candidateCount }}</a-descriptions-item>
            <a-descriptions-item label="已有预测结果">{{ resultCount }}</a-descriptions-item>
          </a-descriptions>
          <div class="stage-actions">
            <a-button type="primary" :disabled="!proteinId" @click="goProteinPredict">
              去亲和力预测
            </a-button>
            <span class="stage-note">结合目标蛋白与候选分子结构，输出结合亲和力预测评分。</span>
          </div>
        </div>

        <!-- 6. ADMET 预测 -->
        <div v-else-if="currentStage.key === 'admet'" class="stage-panel stage-panel--embed">
          <PropertyPredictSubmit :project-id-override="projectId" />
        </div>

        <!-- 7. 虚拟筛选 -->
        <div v-else class="stage-panel stage-panel--embed">
          <ScreenConfig :project-id-override="projectId" />
        </div>
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import MoleculeGeneration from '@/views/design/MoleculeGeneration.vue'
import PeptideDesign from '@/views/design/PeptideDesign.vue'
import PropertyPredictSubmit from '@/views/predict/PropertyPredictSubmit.vue'
import ScreenConfig from '@/views/screening/ScreenConfig.vue'
import StructurePredictForm from '@/components/design/StructurePredictForm.vue'
import PocketPredictPanel from '@/components/design/PocketPredictPanel.vue'
import { message } from 'ant-design-vue'
import { getTarget, listPockets, listStructures, listTargets } from '@/api/targets'
import { listCandidates } from '@/api/compounds'
import { listProjectResults } from '@/api/results'

const props = defineProps<{ projectId: string; initialStep?: number }>()
const router = useRouter()

const stages = [
  { key: 'structure', title: '结构预测', desc: '为靶点蛋白生成高置信度三维结构，作为后续口袋识别与设计的起点。', hint: '' },
  { key: 'pocket', title: '口袋识别', desc: '在蛋白结构上预测潜在配体结合口袋，并按评分对候选位点排序。', hint: '' },
  { key: 'molecule', title: '分子生成', desc: '围绕靶点与结合口袋开展小分子设计，生成候选分子结构。', hint: '' },
  { key: 'peptide', title: '多肽设计', desc: '根据靶点信息与设计条件生成候选多肽序列。', hint: '' },
  { key: 'affinity', title: '亲和力预测', desc: '结合目标蛋白与候选分子结构，输出亲和力预测评分。', hint: '' },
  { key: 'admet', title: 'ADMET 预测', desc: '对候选小分子批量预测吸收、分布、代谢、毒性等性质。', hint: '' },
  { key: 'screen', title: '虚拟筛选', desc: '将候选分子与受体进行分子对接，筛选高潜力候选物。', hint: '' }
]

const current = ref(props.initialStep ?? 0)
const currentStage = computed(() => stages[current.value] ?? stages[0]!)
const loading = ref(true)
const target = ref<any>(null)
const protein = ref<any>(null)
const structure = ref<any>(null)
const structures = ref<any[]>([])
const structureIdSnapshot = ref<string[]>([])
const structureCount = ref(0)
const pocketCount = ref(0)
const candidateCount = ref(0)
const resultCount = ref(0)

const proteinId = computed(() => protein.value?.id || '')
const structureId = computed(() => structure.value?.id || '')

function onStepChange(index: number) {
  current.value = index
}

function goProteinPredict() {
  if (proteinId.value) {
    router.push(`/proteins/${proteinId.value}/predict`)
  }
}

function goPockets() {
  if (structureId.value) {
    router.push(`/structures/${structureId.value}/pockets`)
  }
}

function goStructureDetail() {
  if (structureId.value) {
    router.push(`/structures/${structureId.value}`)
  }
}

function snapshotStructures() {
  structureIdSnapshot.value = structures.value.map((item: any) => item.id)
}

function handleStageError(msg: string) {
  message.error(msg || '操作失败')
}

async function refreshStructureList(id: string) {
  const response = await listStructures(id)
  structures.value = response.data.items ?? []
  structureCount.value = structures.value.length
  return structures.value
}

async function handleStructureCompleted() {
  if (!proteinId.value) return
  const fresh = await refreshStructureList(proteinId.value)
  const added = fresh.find((item: any) => !structureIdSnapshot.value.includes(item.id)) ?? fresh[0] ?? null
  structure.value = added
  if (added) current.value = 1
}

async function refreshPocketCount() {
  if (!structure.value) return
  const response = await listPockets(structure.value.id)
  pocketCount.value = (response.data.items ?? []).length
}

async function handlePocketPredicted() {
  await refreshPocketCount()
}

async function handlePocketSelected() {
  await refreshPocketCount()
  current.value = 2
}

async function load() {
  if (!props.projectId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const targetResponse = await listTargets(props.projectId, { page: 1, page_size: 1 })
    target.value = targetResponse.data.items?.[0] ?? null
    if (target.value) {
      const targetDetail = await getTarget(target.value.id)
      protein.value = targetDetail.data.proteins?.[0] ?? null
      if (protein.value) {
        const structureResponse = await listStructures(protein.value.id)
        structures.value = structureResponse.data.items ?? []
        structureCount.value = structures.value.length
        structure.value = structures.value[0] ?? null
        if (structure.value) {
          const pocketResponse = await listPockets(structure.value.id)
          pocketCount.value = (pocketResponse.data.items ?? []).length
        }
      }
    }
    const candidateResponse = await listCandidates(props.projectId, { page: 1, page_size: 1 })
    candidateCount.value = candidateResponse.data.total ?? 0
    const resultResponse = await listProjectResults(props.projectId, { page: 1, page_size: 1 })
    resultCount.value = resultResponse.data.total ?? 0
  } catch {
    // 数据加载失败时保持空态，不阻断向导使用
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.guided-workflow {
  padding: 8px 4px 24px;
}
.guided-steps {
  margin-bottom: 20px;
}
.guided-steps :deep(.ant-steps-item) {
  min-width: 0;
  flex: 1 1 0;
}
.guided-steps :deep(.ant-steps-item-title) {
  font-size: 12px;
  white-space: nowrap;
}
.guided-steps :deep(.ant-steps-item-icon) {
  margin-inline-end: 6px;
}
.guided-body {
  border: 1px solid var(--color-border-secondary);
  border-radius: 10px;
  padding: 20px;
  background: var(--color-bg-container);
}
.stage-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.stage-title {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
}
.stage-desc {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 13px;
}
.stage-actions {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.stage-note {
  color: var(--color-text-tertiary);
  font-size: 12px;
}
.stage-panel--embed :deep(.app-page-header),
.stage-panel--embed :deep(.back-link) {
  display: none;
}
.stage-panel--embed :deep(main) {
  padding: 0;
  background: transparent;
}
</style>
