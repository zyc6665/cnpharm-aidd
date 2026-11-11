<template>
  <div class="achievements-page">
    <AppPageHeader
      title="项目成果总览"
      subtitle="按项目 / 靶点汇总研发进展、结构与口袋、候选物和计算结果，用于日常查看项目走到了哪一步。"
    >
      <template #actions>
        <a-select
          v-model:value="projectId"
          class="header-select"
          :options="projectOptions"
          placeholder="选择项目"
          @change="onProjectChange"
        />
        <a-select
          v-if="targetOptions.length"
          v-model:value="targetId"
          class="header-select"
          :options="targetOptions"
          placeholder="选择靶点"
          @change="onTargetChange"
        />
        <a-button :loading="refreshing" @click="manualRefresh">
          <ReloadOutlined />
          刷新
        </a-button>
        <span class="updated-text">{{ updatedText }}</span>
      </template>
    </AppPageHeader>

    <a-spin :spinning="loading">
      <!-- 首屏看板：研发阶段 + 待处理 -->
      <div class="hero-grid">
        <a-card class="hero-card hero-stage" :bordered="false">
          <div class="hero-head">
            <span class="hero-title">研发进展</span>
            <a-tag color="processing">{{ stage?.stageName || '未开始' }}</a-tag>
          </div>
          <a-steps
            class="hero-steps"
            size="small"
            :current="currentStageIndex"
            :items="stageItems"
          />
          <div class="hero-foot">
            <span>当前阶段：<b>{{ stage?.stageName || '-' }}</b></span>
            <span v-if="nextStageName">下一步：{{ nextStageName }}</span>
            <span v-else>已到最后一阶段</span>
          </div>
        </a-card>

        <a-card class="hero-card hero-todo" :bordered="false">
          <div class="hero-head">
            <span class="hero-title">待处理</span>
            <a-tag v-if="gaps.length" color="warning">{{ gaps.length }} 项待办</a-tag>
          </div>
          <div v-if="!gaps.length" class="todo-empty">
            <span class="todo-ok">✓</span> 暂无阻塞，项目进展正常
          </div>
          <div v-else class="todo-list">
            <div v-for="(gap, index) in gaps" :key="index" class="todo-item">
              <div class="todo-msg">{{ gap.message }}</div>
              <div class="todo-action">
                <span>{{ gap.action }}</span>
                <a v-if="gap.link" @click="goTo(gap.link)">去处理 →</a>
              </div>
            </div>
          </div>
        </a-card>
      </div>

      <!-- 关键指标 -->
      <div class="metric-grid">
        <div v-for="metric in metrics" :key="metric.label" class="metric-card">
          <div class="metric-label">{{ metric.label }}</div>
          <div class="metric-value">{{ metric.value }}</div>
          <div class="metric-hint">{{ metric.hint }}</div>
        </div>
      </div>

      <!-- 详情区 -->
      <a-card class="panel-card detail-card" :bordered="false">
        <div class="detail-head">
          <a-segmented v-model:value="detailView" :options="detailOptions" />
          <div class="detail-actions">
            <a-button v-if="structureId" size="small" @click="goStructureDetail">
              结构详情
            </a-button>
            <a-button size="small" type="primary" ghost @click="goWorkflow">
              去工作流发起任务
            </a-button>
          </div>
        </div>

        <!-- 结构与口袋 -->
        <div v-if="detailView === 'structure'">
          <a-empty v-if="!structureId" description="该项目还没有可用的蛋白结构">
            <a-button type="primary" @click="goTargets">去导入 / 预测结构</a-button>
          </a-empty>

          <template v-else>
            <!-- 一个蛋白经常有多个结构（重复预测 / 导入 / 准备后各一条），
                 而口袋与残基挂在结构 id 上。没有这个选择器，用户只能看最新的那个，
                 早先结构上的口袋与残基就再也点不到。 -->
            <div class="structure-bar">
              <span class="structure-bar__label">蛋白结构</span>
              <a-select
                v-model:value="structureId"
                class="structure-bar__select"
                :options="structureOptions"
                data-testid="structure-select"
                @change="handleStructureChange"
              />
              <span class="structure-bar__hint">
                共 {{ structures.length }} 个结构 · 切换后口袋与残基跟随所选结构
              </span>
            </div>

            <div class="pocket-layout">
              <div class="pocket-list">
                <div class="section-title">
                  候选结合口袋
                  <span class="section-hint">按预测评分排序 · 点击行切换口袋</span>
                </div>
                <div
                  v-if="!pocketLoading && !pocketRows.length"
                  class="pocket-empty"
                  data-testid="pocket-empty-state"
                >
                  <a-empty description="该结构还没有口袋记录" />
                  <p class="pocket-empty-hint">
                    口袋是按结构预测的：如果口袋是在另一个结构上跑的，请在上方切换结构查看；
                    否则可以到工作流发起一次口袋预测。
                  </p>
                </div>
                <a-table
                  v-else
                  size="small"
                  :columns="pocketColumns"
                  :data-source="pocketRows"
                  :pagination="false"
                  :row-class-name="pocketRowClass"
                  :custom-row="pocketRowEvents"
                  :loading="pocketLoading"
                />
              </div>
              <div class="viewer-card">
                <PocketViewer
                  v-if="pdbUrl"
                  :pdb-url="pdbUrl"
                  :res-ids="pocketResIds"
                  :selected-res-ids="selectedResIds"
                  :pocket-center="pocketCenter"
                  :chain="pocketChain"
                />
                <div v-else class="viewer-empty">
                  <a-empty
                    description="该结构没有可渲染的坐标文件，请到结构详情页准备 / 上传 PDB"
                  >
                    <a-button @click="goStructureDetail">去结构详情</a-button>
                  </a-empty>
                </div>
                <div class="viewer-caption">
                  <template v-if="pdbFallback">
                    坐标来源：本地示例结构（{{ structureFileHint }}）
                  </template>
                  <template v-else>坐标来源：结构文件（{{ structureFileHint }}）</template>
                </div>
              </div>
            </div>

            <div v-if="selectedPocket" class="pocket-detail">
              <div class="residue-panel">
                <div class="section-title">
                  关键残基
                  <span class="section-hint">
                    按口袋内评分从高到低 · 点击可在 3D 中多选高亮
                  </span>
                </div>
                <div v-if="keyResidues.length" class="residue-actions">
                  <a-button size="small" @click="selectAllKeyResidues">全选关键残基</a-button>
                  <a-button size="small" :disabled="!selectedResIds.length" @click="clearResidueSelection">
                    清空选择
                  </a-button>
                  <span class="residue-selected-count">已选 {{ selectedResIds.length }} / {{ keyResidues.length }}</span>
                </div>
                <div v-if="keyResidues.length" class="key-residue-list">
                  <div
                    v-for="(residue, index) in keyResidues"
                    :key="residue.id"
                    class="key-residue"
                    :class="{
                      'key-residue--core': residue.score_tier === 'core',
                      'key-residue--key': residue.score_tier === 'key',
                      'key-residue--active': selectedResIds.includes(residue.residue_seq ?? -1)
                    }"
                    :data-testid="`residue-chip-${residue.residue_seq}`"
                    @click="toggleResidue(residue.residue_seq)"
                  >
                    <span class="kr-rank">{{ index + 1 }}</span>
                    <span class="kr-name">{{ residue.residue_name }}{{ residue.residue_seq }}</span>
                    <span class="kr-chinese">{{ propertyOf(residue.residue_name).chinese }}</span>
                    <a-tag :color="residueCategoryColor(propertyOf(residue.residue_name).category)">
                      {{ propertyOf(residue.residue_name).category }}
                    </a-tag>
                    <span class="kr-score">
                      {{ residue.contribution !== null ? residue.contribution.toFixed(2) : '-' }}
                    </span>
                    <a-tag :color="tierTagColor(residue.score_tier)" data-testid="residue-tier-tag">
                      {{ tierLabel(residue.score_tier) }}
                    </a-tag>
                  </div>
                </div>
                <div v-else class="residue-empty">
                  该口袋暂未存储残基注释数据，仍可在 3D 中查看整个蛋白结构。
                </div>
                <div v-if="selectedSummary" class="residue-detail" data-testid="residue-selection-detail">
                  {{ selectedSummary }}
                </div>

                <div class="section-title all-residues-title">
                  全部残基
                  <span class="section-hint">完整清单（{{ allResidueRows.length }}），此处不列分数</span>
                </div>
                <a-table
                  size="small"
                  class="all-residues-table"
                  :columns="allResidueColumns"
                  :data-source="allResidueRows"
                  :pagination="{ pageSize: 10, size: 'small', showSizeChanger: false }"
                  :row-class-name="allResidueRowClass"
                  :custom-row="allResidueRowEvents"
                  data-testid="all-residues-table"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'residue'">
                      <span class="mono">{{ record.residue_name }}{{ record.residue_seq }}</span>
                    </template>
                    <template v-else-if="column.key === 'category'">
                      <a-tag :color="residueCategoryColor(record.category)">{{ record.category }}</a-tag>
                    </template>
                    <template v-else-if="column.key === 'tier'">
                      <a-tag :color="tierTagColor(record.tier)">{{ tierLabel(record.tier) }}</a-tag>
                    </template>
                  </template>
                </a-table>
              </div>
              <div class="pocket-meta">
                <a-descriptions :column="1" size="small" bordered>
                  <a-descriptions-item label="口袋位点">{{ selectedPocket.id }}</a-descriptions-item>
                  <a-descriptions-item label="预测工具">
                    {{ selectedPocket.tool?.name }} {{ selectedPocket.tool?.version }}
                  </a-descriptions-item>
                  <a-descriptions-item label="评分">
                    {{ formatNumber(selectedPocket.score, 2) }}
                  </a-descriptions-item>
                  <a-descriptions-item label="体积">≈ {{ formatNumber(selectedPocket.volume, 1) }} Å³</a-descriptions-item>
                  <a-descriptions-item label="中心坐标">{{ formatCenter(selectedPocket.center) }}</a-descriptions-item>
                  <a-descriptions-item label="残基数">{{ selectedPocket.residue_count ?? pocketResidues.length }}</a-descriptions-item>
                </a-descriptions>
              </div>
            </div>
          </template>
        </div>

        <!-- 候选物 -->
        <div v-else-if="detailView === 'candidates'">
          <div class="detail-toolbar">
            <a-segmented v-model:value="candidateFilter" :options="candidateFilterOptions" size="small" />
            <span class="toolbar-hint">共 {{ filteredCandidates.length }} 个候选物</span>
          </div>
          <a-empty v-if="!candidates.length" description="该项目还没有候选物">
            <a-button type="primary" @click="goDesign">去发起分子 / 多肽设计</a-button>
          </a-empty>
          <a-table
            v-else
            size="small"
            :columns="candidateColumns"
            :data-source="filteredCandidates"
            :pagination="false"
            row-key="id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'type'">
                <a-tag :color="record.candidate_type === 'PEPTIDE' ? 'purple' : 'blue'">
                  {{ record.candidate_type === 'PEPTIDE' ? '多肽' : '小分子' }}
                </a-tag>
              </template>
              <template v-else-if="column.key === 'substance'">
                <div class="candidate-substance">
                  <span v-if="record.candidate_type === 'PEPTIDE'" class="mono">
                    {{ record.peptide_sequence }}
                  </span>
                  <Smiles2DCell
                    v-else-if="record.compound?.canonical_smiles"
                    :smiles="record.compound.canonical_smiles"
                    :width="132"
                    :height="72"
                  />
                  <span v-else class="mono">—</span>
                </div>
              </template>
              <template v-else-if="column.key === 'weight'">
                {{ record.compound?.mol_weight ? formatNumber(record.compound.mol_weight, 1) : '-' }}
              </template>
              <template v-else-if="column.key === 'score'">
                {{ formatNumber(record.design_score, 3) }}
              </template>
              <template v-else-if="column.key === 'prediction'">
                <a-tooltip title="到亲和力 / ADMET 预测页发起计算">
                  <a-tag color="default" class="clickable-tag" @click="goPredict">未预测</a-tag>
                </a-tooltip>
              </template>
            </template>
          </a-table>
        </div>

        <!-- 亲和力与 ADMET -->
        <div v-else>
          <a-empty
            v-if="!results.length"
            description="暂无亲和力 / ADMET 预测结果"
          >
            <div class="empty-note">
              候选物生成后，在「亲和力预测」或「虚拟筛选」页发起计算，结果会自动汇总到这里。
            </div>
            <a-space>
              <a-button type="primary" @click="goPredict">去亲和力 / ADMET 预测</a-button>
              <a-button @click="goScreen">去虚拟筛选</a-button>
            </a-space>
          </a-empty>
          <template v-else>
            <div class="section-title">
              计算结果
              <span class="section-hint">共 {{ results.length }} 条</span>
            </div>
            <a-table
              size="small"
              :columns="resultColumns"
              :data-source="resultRows"
              :pagination="false"
              row-key="task_id"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'status'">
                  <a-tag :color="resultStatusColor(record.status)">{{ record.status }}</a-tag>
                </template>
                <template v-else-if="column.key === 'action'">
                  <a @click="goResult(record.task_id)">查看结果 →</a>
                </template>
              </template>
            </a-table>
          </template>
        </div>
      </a-card>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'

import AppPageHeader from '@/components/common/AppPageHeader.vue'
import PocketViewer from '@/components/tasks/PocketViewer.vue'
import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'

import { listProjects } from '@/api/projects'
import { residueCategoryColor, residuePropertyOf } from '@/domain/targets/residue-property'
import {
  sortStructuresByNewest,
  structureOptionLabel
} from '@/domain/targets/structure-option'
import {
  getStructurePdbManifest,
  getTarget,
  listPocketResidues,
  listPockets,
  listStructures,
  listTargets
} from '@/api/targets'
import { listCandidates } from '@/api/compounds'
import { getProjectStage, listProjectDecisions } from '@/api/decisions'
import { getWorkflowRuns } from '@/api/workflows'
import { listProjectResults } from '@/api/results'

import type { ResearchProject } from '@/types/projects'
import type {
  PocketResidue,
  PocketResidueTier,
  PocketSummary,
  ProteinStructureDetail,
  TargetSummary
} from '@/types/targets'
import type { Candidate } from '@/types/compounds'
import type { ProjectResultSummary } from '@/types/compounds'
import type { DecisionRecord, ProjectStage } from '@/types/decisions'
import type { WorkflowRun } from '@/types/models'

const route = useRoute()
const router = useRouter()

const STAGES = [
  { key: 'S0', name: '立项与数据归集', short: '立项' },
  { key: 'S1', name: '靶点确立', short: '靶点' },
  { key: 'S2', name: '结构与口袋就绪', short: '结构口袋' },
  { key: 'S3', name: '候选生成', short: '候选' },
  { key: 'S4', name: '性质评估', short: '性质' },
  { key: 'S5', name: '计算验证', short: '验证' },
  { key: 'S6', name: '决策与归档', short: '决策' }
]

const loading = ref(false)
const refreshing = ref(false)
const pocketLoading = ref(false)
const updatedAt = ref<Date | null>(null)

const projects = ref<ResearchProject[]>([])
const projectId = ref('')

const targets = ref<TargetSummary[]>([])
const targetId = ref('')
const targetDetail = ref<TargetSummary | null>(null)

const structures = ref<ProteinStructureDetail[]>([])
const structureId = ref('')

const structureOptions = computed(() =>
  structures.value.map((structure) => ({
    value: structure.id,
    label: structureOptionLabel(structure)
  }))
)

const pockets = ref<PocketSummary[]>([])
const selectedPocketId = ref('')
const pocketResidues = ref<PocketResidue[]>([])
const selectedResIds = ref<number[]>([])

const pdbUrl = ref('')
const pdbFallback = ref(false)

const stage = ref<ProjectStage | null>(null)
const candidates = ref<Candidate[]>([])
const decisions = ref<DecisionRecord[]>([])
const runs = ref<WorkflowRun[]>([])
const results = ref<ProjectResultSummary[]>([])

const detailView = ref<'structure' | 'candidates' | 'admet'>('structure')
const candidateFilter = ref<'ALL' | 'SMALL_MOLECULE' | 'PEPTIDE'>('ALL')

const detailOptions = [
  { label: '结构与口袋', value: 'structure' },
  { label: '候选物', value: 'candidates' },
  { label: '亲和力与 ADMET', value: 'admet' }
]

const candidateFilterOptions = [
  { label: '全部', value: 'ALL' },
  { label: '小分子', value: 'SMALL_MOLECULE' },
  { label: '多肽', value: 'PEPTIDE' }
]

const projectOptions = computed(() =>
  projects.value.map((project) => ({ label: project.name, value: project.id }))
)

const targetOptions = computed(() =>
  targets.value.map((target) => ({
    label: target.gene_name ? `${target.name}（${target.gene_name}）` : target.name,
    value: target.id
  }))
)

const stageItems = computed(() => STAGES.map((item) => ({ title: item.short })))

const currentStageIndex = computed(() => {
  const key = stage.value?.currentStage
  const index = STAGES.findIndex((item) => item.key === key)
  return index >= 0 ? index : 0
})

const nextStageName = computed(() => {
  const key = stage.value?.nextStage
  if (!key) return ''
  return STAGES.find((item) => item.key === key)?.name ?? ''
})

const gaps = computed(() => stage.value?.gaps ?? [])

const metrics = computed(() => {
  const counters = stage.value?.counters
  const smallMolecules = candidates.value.filter((item) => item.candidate_type === 'SMALL_MOLECULE').length
  const peptides = candidates.value.filter((item) => item.candidate_type === 'PEPTIDE').length
  return [
    { label: '靶点', value: counters?.targets ?? 0, hint: '已登记靶点' },
    { label: '蛋白结构', value: counters?.structures ?? 0, hint: '可用结构' },
    { label: '口袋位点', value: counters?.selected_pockets ?? 0, hint: '已选定口袋' },
    {
      label: '候选物',
      value: counters?.candidates ?? 0,
      hint: `小分子 ${smallMolecules} · 多肽 ${peptides}`
    },
    { label: '决策记录', value: counters?.decisions ?? decisions.value.length, hint: '研发决策' },
    {
      label: '计算任务',
      value: `${counters?.finished_tasks ?? 0}/${counters?.submitted_tasks ?? 0}`,
      hint: '完成 / 提交'
    }
  ]
})

const pocketRows = computed(() =>
  pockets.value.map((pocket) => ({
    ...pocket,
    key: pocket.id,
    scoreText: formatNumber(pocket.score, 2),
    volumeText: formatNumber(pocket.volume, 1),
    centerText: formatCenter(pocket.center)
  }))
)

const pocketColumns = [
  { title: '排名', dataIndex: 'rank', key: 'rank', width: 56 },
  { title: '评分', dataIndex: 'scoreText', key: 'score', width: 64 },
  { title: '体积', dataIndex: 'volumeText', key: 'volume', width: 72 },
  { title: '残基', dataIndex: 'residue_count', key: 'residue_count', width: 56 },
  {
    title: '状态',
    key: 'selected',
    width: 72,
    customRender: ({ record }: { record: PocketSummary }) =>
      record.id === selectedPocketId.value ? '已选定' : ''
  }
]

const selectedPocket = computed(
  () => pockets.value.find((pocket) => pocket.id === selectedPocketId.value) ?? null
)

const pocketResIds = computed(() =>
  pocketResidues.value
    .map((residue) => residue.residue_seq)
    .filter((seq): seq is number => typeof seq === 'number')
)

const pocketCenter = computed<[number, number, number] | null>(() => {
  const center = selectedPocket.value?.center
  if (!center) return null
  const { x, y, z } = center
  if (typeof x !== 'number' || typeof y !== 'number' || typeof z !== 'number') return null
  return [x, y, z]
})

const pocketChain = computed(() => pocketResidues.value[0]?.chain || 'A')

/**
 * 按口袋内评分排序。
 *
 * 口袋残基是「距口袋点 8 Å 内」的整份清单，按残基序号排等于把「先看哪几个」
 * 这个问题丢回用户。没有分数的历史行排在最后，不当作 0 分混进末尾——那会让
 * 「没算过」和「算了很低」长得一样。
 */
const rankedResidues = computed(() =>
  [...pocketResidues.value].sort((left, right) => {
    const a = left.contribution ?? Number.NEGATIVE_INFINITY
    const b = right.contribution ?? Number.NEGATIVE_INFINITY
    if (a !== b) return b - a
    return (left.residue_seq ?? 0) - (right.residue_seq ?? 0)
  })
)

function tierLabel(tier: PocketResidueTier | null | undefined): string {
  if (tier === 'core') return '核心残基'
  if (tier === 'key') return '关键残基'
  if (tier === 'peripheral') return '外围残基'
  return '未评分'
}

function tierTagColor(tier: PocketResidueTier | null | undefined): string {
  if (tier === 'core') return 'orange'
  if (tier === 'key') return 'gold'
  return 'default'
}

/**
 * 「关键残基」只列核心与关键两级。
 *
 * 用户要的是「先看哪几个」，把 99 个残基连分数一起铺开等于没给结论；
 * 外围残基留在下面的「全部残基」清单里备查，不在主视图占版面。
 */
const keyResidues = computed(() =>
  rankedResidues.value.filter(
    (residue) => residue.score_tier === 'core' || residue.score_tier === 'key'
  )
)

const allResidueRows = computed(() =>
  rankedResidues.value.map((residue, index) => {
    const property = residuePropertyOf(residue.residue_name)
    return {
      key: residue.id ?? `${residue.residue_seq}-${index}`,
      residue_seq: residue.residue_seq,
      residue_name: residue.residue_name,
      chain: residue.chain,
      chinese: property.chinese,
      category: property.category,
      hydropathy: property.hydropathy,
      tier: residue.score_tier ?? null
    }
  })
)

const allResidueColumns = [
  { title: '残基', key: 'residue', width: 96 },
  { title: '中文名', dataIndex: 'chinese', key: 'chinese', width: 96 },
  { title: '类别', key: 'category', width: 84 },
  { title: '疏水指数', dataIndex: 'hydropathy', key: 'hydropathy', width: 90 },
  { title: '分级', key: 'tier', width: 90 }
]

function allResidueRowClass(record: { residue_seq: number | null }): string {
  return selectedResIds.value.includes(record.residue_seq ?? -1) ? 'all-residues-row--active' : ''
}

function allResidueRowEvents(record: { residue_seq: number | null }) {
  return { onClick: () => toggleResidue(record.residue_seq) }
}

function propertyOf(name: string | null | undefined) {
  return residuePropertyOf(name)
}

function toggleResidue(seq: number | null | undefined) {
  if (typeof seq !== 'number') return
  const index = selectedResIds.value.indexOf(seq)
  if (index >= 0) {
    selectedResIds.value = selectedResIds.value.filter((item) => item !== seq)
  } else {
    selectedResIds.value = [...selectedResIds.value, seq]
  }
}

function selectAllKeyResidues() {
  selectedResIds.value = keyResidues.value
    .map((residue) => residue.residue_seq)
    .filter((seq): seq is number => typeof seq === 'number')
}

function clearResidueSelection() {
  selectedResIds.value = []
}

/** 选中集的一句话摘要：选 1 个给细节，选多个给清单。 */
const selectedSummary = computed(() => {
  if (!selectedResIds.value.length) return ''
  const picked = rankedResidues.value.filter(
    (residue) => residue.residue_seq != null && selectedResIds.value.includes(residue.residue_seq)
  )
  if (!picked.length) return ''
  if (picked.length === 1) {
    const residue = picked[0]
    if (!residue) return ''
    const property = residuePropertyOf(residue.residue_name)
    return [
      `${residue.residue_name}${residue.residue_seq}`,
      property.chinese,
      `${property.category}性`,
      `疏水指数 ${property.hydropathy.toFixed(1)}`,
      `链 ${residue.chain || '-'}`,
      tierLabel(residue.score_tier),
      `评分 ${residue.contribution !== null ? residue.contribution.toFixed(2) : '-'}`
    ].join(' · ')
  }
  return `已选 ${picked.length} 个残基：${picked
    .map((residue) => `${residue.residue_name}${residue.residue_seq}`)
    .join('、')}`
})

const structureFileHint = computed(() => {
  const structure = structures.value.find((item) => item.id === structureId.value)
  return structure?.structure_urn?.split('/').pop() || structureId.value
})

const filteredCandidates = computed(() => {
  if (candidateFilter.value === 'ALL') return candidates.value
  return candidates.value.filter((item) => item.candidate_type === candidateFilter.value)
})

const candidateColumns = [
  { title: '类型', key: 'type', width: 74 },
  { title: '名称', dataIndex: 'name', key: 'name', width: 150 },
  { title: '代号', dataIndex: 'code', key: 'code', width: 110 },
  {
    title: '结构 / 序列',
    key: 'substance',
    width: 168
  },
  { title: '分子量', key: 'weight', width: 84 },
  { title: '设计评分', key: 'score', width: 84 },
  { title: '亲和力 / ADMET', key: 'prediction', width: 120 }
]

const resultRows = computed(() =>
  results.value.map((item) => ({
    ...item,
    createdText: formatDateTime(item.created_at),
    durationText: item.execution_time_sec ? `${Math.round(item.execution_time_sec)} s` : '-'
  }))
)

const resultColumns = [
  { title: '任务名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '工具', dataIndex: 'tool_name', key: 'tool_name', width: 150 },
  { title: '状态', key: 'status', width: 100 },
  { title: '提交时间', dataIndex: 'createdText', key: 'createdText', width: 160 },
  { title: '耗时', dataIndex: 'durationText', key: 'durationText', width: 80 },
  { title: '操作', key: 'action', width: 100 }
]

const updatedText = computed(() => {
  if (!updatedAt.value) return ''
  return `更新于 ${formatClock(updatedAt.value)}`
})

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return Number(value).toFixed(digits)
}

function formatCenter(
  center: { x?: number | null; y?: number | null; z?: number | null } | null | undefined
): string {
  if (!center) return '-'
  const { x, y, z } = center
  if (typeof x !== 'number' || typeof y !== 'number' || typeof z !== 'number') return '-'
  return `${x.toFixed(1)}, ${y.toFixed(1)}, ${z.toFixed(1)}`
}

function formatClock(value: Date): string {
  return value.toLocaleTimeString('zh-CN', { hour12: false })
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function resultStatusColor(status: string): string {
  if (status === 'success') return 'success'
  if (status === 'failure' || status === 'failed') return 'error'
  if (status === 'running') return 'processing'
  return 'default'
}

function pocketRowClass(record: PocketSummary): string {
  return record.id === selectedPocketId.value ? 'pocket-row--active' : ''
}

function pocketRowEvents(record: PocketSummary) {
  return {
    onClick: () => selectPocket(record.id)
  }
}

async function loadProjects() {
  try {
    const response = await listProjects()
    projects.value = response.data.items ?? []
    const queryProject = typeof route.query.projectId === 'string' ? route.query.projectId : ''
    const preferred = projects.value.find((project) => project.id === queryProject)
    projectId.value = preferred?.id ?? projects.value[0]?.id ?? ''
  } catch {
    projects.value = []
  }
}

async function loadTargets() {
  if (!projectId.value) return
  try {
    const response = await listTargets(projectId.value)
    targets.value = response.data.items ?? []
    const queryTarget = typeof route.query.targetId === 'string' ? route.query.targetId : ''
    const preferred = targets.value.find((target) => target.id === queryTarget)
    targetId.value = preferred?.id ?? targets.value[0]?.id ?? ''
  } catch {
    targets.value = []
    targetId.value = ''
  }
}

async function loadTargetContext() {
  structures.value = []
  structureId.value = ''
  pockets.value = []
  pocketResidues.value = []
  selectedPocketId.value = ''
  selectedResIds.value = []
  clearPdb()

  if (!targetId.value) {
    targetDetail.value = null
    return
  }

  try {
    const response = await getTarget(targetId.value)
    targetDetail.value = response.data
    const protein = response.data.proteins?.[0]
    if (!protein) return
    const structureResponse = await listStructures(protein.id)
    structures.value = sortStructuresByNewest(structureResponse.data.items ?? [])
    structureId.value = structures.value[0]?.id ?? ''
  } catch {
    targetDetail.value = null
    structures.value = []
    structureId.value = ''
  }

  if (structureId.value) {
    await Promise.all([loadPockets(structureId.value), loadPdb(structureId.value)])
  }
}

/**
 * 切换蛋白结构。
 *
 * 口袋与残基都挂在**结构** id 上，不是挂在蛋白或项目上：同一个蛋白重新预测一次，
 * 新的结构没有任何口袋，旧结构上的口袋与残基也不会跟过来。所以切换时必须把
 * 上一个结构的口袋、选中口袋与选中残基全部清掉，再用新 id 重新拉取。
 */
async function handleStructureChange(value: unknown) {
  const nextId = String(value || '')
  if (!nextId) return
  structureId.value = nextId
  pockets.value = []
  pocketResidues.value = []
  selectedPocketId.value = ''
  selectedResIds.value = []
  clearPdb()
  await Promise.all([loadPockets(nextId), loadPdb(nextId)])
}

async function loadPockets(id: string) {  pocketLoading.value = true
  try {
    const response = await listPockets(id)
    pockets.value = [...(response.data.items ?? [])].sort(
      (a, b) => (a.rank ?? 999) - (b.rank ?? 999)
    )
    if (pockets.value.length) {
      const firstPocket = pockets.value[0]
      if (firstPocket) await selectPocket(firstPocket.id)
    }
  } catch {
    pockets.value = []
  } finally {
    pocketLoading.value = false
  }
}

async function selectPocket(id: string) {
  selectedPocketId.value = id
  pocketResidues.value = []
  selectedResIds.value = []
  try {
    const response = await listPocketResidues(id)
    pocketResidues.value = response.data.items ?? []
    // 默认选中排名第一的残基：「清单第一个」和「最值得先看的那个」不是同一件事
    const top = rankedResidues.value[0]?.residue_seq
    selectedResIds.value = typeof top === 'number' ? [top] : []
  } catch {
    pocketResidues.value = []
  }
}

function clearPdb() {
  if (pdbUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(pdbUrl.value)
  }
  pdbUrl.value = ''
  pdbFallback.value = false
}

async function loadPdb(id: string) {
  clearPdb()
  try {
    const response = await getStructurePdbManifest(id)
    const primary =
      response.data.files.find((file) => file.download_url) ?? response.data.files[0]
    if (primary?.download_url) {
      pdbUrl.value = primary.download_url
      return
    }
  } catch {
    // 结构没有可下载文件时回退到本地示例坐标
  }

  const structure = structures.value.find((item) => item.id === id)
  const filename = structure?.structure_urn?.split('/').pop()
  if (!filename) return
  try {
    const response = await fetch(`/demo/${filename}`)
    if (!response.ok) return
    const text = await response.text()
    pdbUrl.value = URL.createObjectURL(new Blob([text], { type: 'chemical/x-pdb' }))
    pdbFallback.value = true
  } catch {
    pdbUrl.value = ''
  }
}

async function loadStage() {
  try {
    const response = await getProjectStage(projectId.value)
    stage.value = response.data
  } catch {
    stage.value = null
  }
}

async function loadCandidates() {
  try {
    const response = await listCandidates(projectId.value, { page: 1, page_size: 100 })
    candidates.value = response.data.items ?? []
  } catch {
    candidates.value = []
  }
}

async function loadDecisions() {
  try {
    const response = await listProjectDecisions(projectId.value, { page: 1, page_size: 10 })
    decisions.value = response.data.items ?? []
  } catch {
    decisions.value = []
  }
}

async function loadRuns() {
  try {
    const response = await getWorkflowRuns({ project_id: projectId.value, page: 1, page_size: 10 })
    runs.value = response.data.items ?? []
  } catch {
    runs.value = []
  }
}

async function loadResults() {
  try {
    const response = await listProjectResults(projectId.value, { page: 1, page_size: 50 })
    results.value = response.data.items ?? []
  } catch {
    results.value = []
  }
}

async function loadProject() {
  if (!projectId.value) return
  loading.value = true
  try {
    await loadTargets()
    await Promise.all([loadStage(), loadCandidates(), loadDecisions(), loadRuns(), loadResults()])
    await loadTargetContext()
    updatedAt.value = new Date()
  } finally {
    loading.value = false
  }
}

async function manualRefresh() {
  refreshing.value = true
  try {
    await loadProject()
    message.success('已刷新')
  } finally {
    refreshing.value = false
  }
}

function onProjectChange() {
  router.replace({ query: { ...route.query, projectId: projectId.value } })
  loadProject()
}

function onTargetChange() {
  router.replace({ query: { ...route.query, targetId: targetId.value } })
  loadTargetContext()
}

function goTo(link: string | null) {
  if (link) router.push(link)
}

function goTargets() {
  router.push(`/projects/${projectId.value}/targets`)
}

function goStructureDetail() {
  if (structureId.value) router.push(`/structures/${structureId.value}`)
}

function goWorkflow() {
  router.push(projectId.value ? `/projects/${projectId.value}/workflow` : '/workflow')
}

function goDesign() {
  router.push('/design/molecules')
}

function goPredict() {
  router.push({ path: '/predict', query: { projectId: projectId.value } })
}

function goScreen() {
  router.push({ path: '/screen', query: { projectId: projectId.value } })
}

function goResult(taskId: string) {
  router.push(`/results/${taskId}`)
}

onMounted(async () => {
  await loadProjects()
  await loadProject()
})

onBeforeUnmount(() => {
  clearPdb()
})
</script>

<style scoped lang="less">
.achievements-page {
  padding: 24px;
}
.header-select {
  width: 190px;
}
.updated-text {
  font-size: 12px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.hero-card {
  background: var(--color-bg-container);
  border: 1px solid var(--color-border-secondary);
  border-radius: 12px;
}
.hero-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.hero-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.hero-steps {
  padding: 4px 0 2px;
}
.hero-foot {
  display: flex;
  gap: 24px;
  margin-top: 18px;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.hero-foot b {
  color: var(--color-text-primary);
}
.todo-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 18px 0;
  color: var(--color-text-secondary);
  font-size: 13px;
}
.todo-ok {
  color: var(--color-success, #52c41a);
  font-weight: 700;
}
.todo-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.todo-item {
  padding: 12px 14px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 10px;
  background: var(--theme-accent-light, rgba(255, 122, 69, 0.06));
}
.todo-msg {
  font-size: 13px;
  color: var(--color-text-primary);
  margin-bottom: 6px;
}
.todo-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.metric-card {
  background: var(--color-bg-container);
  border: 1px solid var(--color-border-secondary);
  border-radius: 10px;
  padding: 14px 16px;
}
.metric-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
}
.metric-value {
  font-size: 22px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.2;
}
.metric-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.panel-card {
  background: var(--color-bg-container);
  border: 1px solid var(--color-border-secondary);
  border-radius: 12px;
}
.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.detail-actions {
  display: flex;
  gap: 8px;
}
.detail-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.toolbar-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 10px;
}
.section-hint {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--color-text-tertiary);
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
  color: var(--color-text-primary);
}
.structure-bar__select {
  width: 420px;
  max-width: 100%;
}
.structure-bar__hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.pocket-empty {
  padding: 12px 0;
}
.pocket-empty-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-tertiary);
}

.pocket-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr);
  gap: 16px;
  margin-bottom: 16px;
}
.pocket-list :deep(.ant-table-tbody > tr) {
  cursor: pointer;
}
.pocket-list :deep(.pocket-row--active > td) {
  background: var(--theme-accent-light, rgba(255, 122, 69, 0.12));
}
.viewer-card {
  border: 1px solid var(--color-border-secondary);
  border-radius: 10px;
  overflow: hidden;
  background: var(--color-bg-container);
  display: flex;
  flex-direction: column;
  min-height: 420px;
}
.viewer-card :deep(.pocket-viewer) {
  flex: 1;
}
.viewer-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 380px;
}
.viewer-caption {
  padding: 8px 14px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  border-top: 1px solid var(--color-border-secondary);
}

.pocket-detail {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  gap: 16px;
}
.residue-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.residue-selected-count {
  font-size: 12px;
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}
.key-residue-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 420px;
  overflow-y: auto;
  padding-right: 4px;
}
.key-residue {
  display: grid;
  grid-template-columns: 28px minmax(72px, auto) minmax(64px, auto) auto minmax(48px, auto) auto;
  align-items: center;
  gap: 10px;
  padding: 5px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--color-bg-layout);
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.key-residue:hover {
  border-color: var(--color-border-secondary);
}
.key-residue--core .kr-name {
  color: #cf1322;
  font-weight: 600;
}
.key-residue--key .kr-name {
  color: #ad6800;
  font-weight: 600;
}
.key-residue--active {
  border-color: #22d3ee;
  background: rgba(34, 211, 238, 0.14);
}
.kr-rank {
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}
.kr-name {
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.kr-chinese {
  color: var(--color-text-secondary);
}
.kr-score {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
}
.residue-empty {
  padding: 10px 12px;
  border: 1px dashed var(--color-border-secondary);
  border-radius: 8px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.residue-detail {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--color-border-secondary);
  font-size: 12px;
  color: var(--color-text-secondary);
}
.all-residues-title {
  margin-top: 18px;
}
.all-residues-table :deep(tr.all-residues-row--active > td) {
  background: rgba(34, 211, 238, 0.1);
}

.candidate-substance {
  font-size: 12px;
}
.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.clickable-tag {
  cursor: pointer;
}
.empty-note {
  max-width: 460px;
  margin: 0 auto 16px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text-secondary);
}

@media (max-width: 1200px) {
  .hero-grid,
  .pocket-layout,
  .pocket-detail {
    grid-template-columns: minmax(0, 1fr);
  }
  .metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
