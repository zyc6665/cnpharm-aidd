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
          <p v-else class="stage-note">{{ t('workflow.guided.noProtein') }}</p>
          <div class="stage-actions">
            <span class="stage-note">{{ t('workflow.guided.structureNote') }}</span>
            <a-button type="link" :disabled="!structureId" @click="goStructureDetail">{{ t('workflow.guided.goStructureDetail') }}</a-button>
          </div>
        </div>

        <!-- 2. 口袋识别（就地） -->
        <div v-else-if="currentStage.key === 'pocket'" class="stage-panel">
          <div class="structure-bar">
            <span class="structure-bar__label">蛋白结构</span>
            <a-select
              v-model:value="selectedStructureId"
              class="structure-bar__select"
              :options="structureOptions"
              :disabled="structureOptions.length < 2"
              data-testid="guided-structure-select"
              @change="handleStructureChange"
            />
            <span class="structure-bar__hint">
              共 {{ structureCount }} 个结构 · 口袋是按结构预测的，切换后表格跟随所选结构
            </span>
          </div>
          <a-descriptions :column="3" size="small" bordered>
            <a-descriptions-item label="可用结构">{{ structureCount }}</a-descriptions-item>
            <a-descriptions-item label="已识别口袋">{{ pocketCount }}</a-descriptions-item>
            <a-descriptions-item label="当前结构口袋">{{ selectedPocketCount }}</a-descriptions-item>
          </a-descriptions>
          <PocketPredictPanel
            v-if="structureId"
            :structure-id="structureId"
            @predicted="handlePocketPredicted"
            @selected="handlePocketSelected"
          />
          <p v-else class="stage-note">{{ t('workflow.guided.noStructure') }}</p>
          <div class="stage-actions">
            <span class="stage-note">{{ t('workflow.guided.pocketNote') }}</span>
            <a-button type="link" :disabled="!structureId" @click="goPockets">{{ t('workflow.guided.goPocketManage') }}</a-button>
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

        <!-- 5. 亲和力预测（就地，与 ADMET 一致） -->
        <div v-else-if="currentStage.key === 'affinity'" class="stage-panel">
          <a-descriptions :column="3" size="small" bordered>
            <a-descriptions-item label="靶点">{{ target?.name || '未登记' }}</a-descriptions-item>
            <a-descriptions-item label="候选物">{{ candidateCount }}</a-descriptions-item>
            <a-descriptions-item label="已有预测结果">{{ resultCount }}</a-descriptions-item>
          </a-descriptions>
          <!-- 亲和力与 ADMET 是同一张页面的两种类型，这里固定成 affinity，
               省掉"去性质预测页再点一下类型"的一跳；完整页面入口保留在下方。 -->
          <PropertyPredictSubmit :project-id-override="projectId" initial-type="affinity" />
          <div class="stage-actions">
            <a-button type="link" @click="goAffinityPredict">在性质预测页打开</a-button>
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
import { useI18n } from 'vue-i18n'
import { selectNewlyAdded } from '@/domain/design/pipeline'
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
import { sortStructuresByNewest, structureOptionLabel } from '@/domain/targets/structure-option'
import type { ProteinDetail, ProteinStructureDetail, TargetSummary } from '@/types/targets'

const props = defineProps<{ projectId: string; initialStep?: number }>()
const router = useRouter()
const { t } = useI18n()

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
const target = ref<TargetSummary | null>(null)
const protein = ref<ProteinDetail | null>(null)
const structures = ref<ProteinStructureDetail[]>([])
const selectedStructureId = ref('')
const structureIdSnapshot = ref<string[]>([])
const structureCount = ref(0)
const pocketCounts = ref<Record<string, number>>({})
const candidateCount = ref(0)
const resultCount = ref(0)
/** 见 handleStructureChange 与 load：晚到的加载响应不能覆盖用户已经做出的选择。 */
let loadToken = 0

const proteinId = computed(() => protein.value?.id || '')
const structureId = computed(() => selectedStructureId.value)
const structureOptions = computed(() =>
  structures.value.map(item => ({ label: structureOptionLabel(item), value: item.id }))
)
/**
 * 已识别口袋按结构汇总。
 *
 * 原来只统计 `structures[0]`（后端按 created_at 倒序，即最新那个），
 * 于是"在旧结构上跑过的口袋"在统计里凭空消失——用户看到「已识别口袋 0」
 * 却明明有一个口袋。统计口径必须是"这个蛋白名下所有结构的口袋之和"。
 */
const pocketCount = computed(() =>
  Object.values(pocketCounts.value).reduce((sum, value) => sum + value, 0)
)
const selectedPocketCount = computed(() => pocketCounts.value[selectedStructureId.value] ?? 0)

function onStepChange(index: number) {
  current.value = index
}

function goAffinityPredict() {
  if (!proteinId.value) return
  router.push({ path: '/predict', query: { type: 'affinity', project_id: props.projectId } })
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
  message.error(msg || t('workflow.guided.actionFailed'))
}

async function refreshStructureList(id: string) {
  const response = await listStructures(id)
  structures.value = sortStructuresByNewest(response.data.items ?? [])
  structureCount.value = structures.value.length
  return structures.value
}

async function handleStructureCompleted() {
  if (!proteinId.value) return
  const fresh = await refreshStructureList(proteinId.value)
  const added = selectNewlyAdded(structureIdSnapshot.value, fresh)
  if (added) selectedStructureId.value = added.id
  await refreshPocketCounts()
  if (added) current.value = 1
}

/** 结构切换：口袋表格由 PocketPredictPanel 自己跟着 structureId 重拉，这里只管选中值与统计。 */
function handleStructureChange(value: unknown) {
  // 用户已经动手选了，就别让还没回来的首次加载把选择覆盖回去。
  loadToken += 1
  selectedStructureId.value = typeof value === 'string' ? value : ''
}

/**
 * 逐结构统计口袋数。单个结构读失败只记 0，不能让整页统计一起失败
 * （否则"已识别口袋"会显示成加载错误，用户以为数据丢了）。
 */
async function refreshPocketCounts() {
  if (!structures.value.length) {
    pocketCounts.value = {}
    return
  }
  const entries = await Promise.all(
    structures.value.map(async (item): Promise<[string, number]> => {
      try {
        const response = await listPockets(item.id)
        return [item.id, (response.data.items ?? []).length]
      } catch {
        return [item.id, 0]
      }
    })
  )
  pocketCounts.value = Object.fromEntries(entries)
}

async function handlePocketPredicted() {
  await refreshPocketCounts()
}

async function handlePocketSelected() {
  await refreshPocketCounts()
  current.value = 2
}

/**
 * 加载令牌：`load()` 会连打四五个接口，用户完全可能在它还没跑完时就开始点结构下拉。
 * 没有这个令牌，晚到的响应会把用户刚选的 structureId 覆盖回"最新那个"——
 * 表现就是"选了另一个结构，表格闪一下又空了"。
 */
async function load() {
  if (!props.projectId) {
    loading.value = false
    return
  }
  const token = ++loadToken
  loading.value = true
  try {
    const targetResponse = await listTargets(props.projectId, { page: 1, page_size: 1 })
    if (token !== loadToken) return
    target.value = targetResponse.data.items?.[0] ?? null
    if (target.value) {
      const targetDetail = await getTarget(target.value.id)
      if (token !== loadToken) return
      protein.value = targetDetail.data.proteins?.[0] ?? null
      if (protein.value) {
        await refreshStructureList(protein.value.id)
        if (token !== loadToken) return
        selectedStructureId.value = structures.value[0]?.id ?? ''
        await refreshPocketCounts()
        if (token !== loadToken) return
      }
    }
    const candidateResponse = await listCandidates(props.projectId, { page: 1, page_size: 1 })
    if (token !== loadToken) return
    candidateCount.value = candidateResponse.data.total ?? 0
    const resultResponse = await listProjectResults(props.projectId, { page: 1, page_size: 1 })
    if (token !== loadToken) return
    resultCount.value = resultResponse.data.total ?? 0
  } catch {
    // 数据加载失败时保持空态，不阻断向导使用
  } finally {
    if (token === loadToken) loading.value = false
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
.structure-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.structure-bar__label {
  font-size: 13px;
  font-weight: 600;
}
.structure-bar__select {
  width: 420px;
  max-width: 100%;
}
.structure-bar__hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
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
