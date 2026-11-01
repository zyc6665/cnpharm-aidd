<template>
  <main class="achievements-page" data-testid="achievements-page">
    <AppPageHeader
      title="项目成果展示"
      subtitle="GRK4 靶向高血压候选药物研发 · 全流程计算评估结果"
    >
      <template #actions>
        <a-tag color="green">项目已完成</a-tag>
      </template>
    </AppPageHeader>

    <section class="summary-grid">
      <a-card v-for="card in summaryCards" :key="card.label" :bordered="false" class="summary-card">
        <div class="summary-label">{{ card.label }}</div>
        <div class="summary-value">{{ card.value }}</div>
        <div class="summary-hint">{{ card.hint }}</div>
      </a-card>
    </section>

    <a-tabs v-model:activeKey="activeTab" class="achievement-tabs">
      <a-tab-pane key="structure" tab="蛋白结构预测">
        <section class="panel-grid">
          <a-card title="序列输入与预测参数" :bordered="false" class="panel-card">
            <div class="field-label">目标蛋白</div>
            <a-input :value="protein.name" readonly />
            <div class="field-label">氨基酸序列（{{ protein.sequence.length }} aa）</div>
            <a-textarea :value="protein.sequence" :rows="6" readonly class="sequence-input" />
            <div class="param-row">
              <div>
                <div class="field-label">预测模型</div>
                <a-input :value="protein.model" readonly />
              </div>
              <div>
                <div class="field-label">循环次数</div>
                <a-input :value="'3'" readonly />
              </div>
              <div>
                <div class="field-label">随机种子</div>
                <a-input :value="'42'" readonly />
              </div>
            </div>
            <a-button type="primary" class="run-button" @click="notifyDone('结构预测任务已完成')">
              开始预测
            </a-button>
          </a-card>

          <a-card title="预测结构（3D）" :bordered="false" class="panel-card viewer-card">
            <MoleculeViewer v-if="scene" :scene="scene" variant="full" />
            <div v-else class="viewer-loading"><a-spin /> 正在加载结构…</div>
            <div class="viewer-caption">GRK4 激酶结构域 · PDB 4YHJ · 卡通模型</div>
          </a-card>
        </section>
      </a-tab-pane>

      <a-tab-pane key="pocket" tab="结合口袋预测">
        <section class="panel-grid">
          <a-card title="口袋评分与成药性" :bordered="false" class="panel-card">
            <a-table
              :columns="pocketColumns"
              :data-source="pockets"
              :pagination="false"
              size="small"
              :row-class-name="(record: PocketRow) => (record.id === selectedPocket ? 'selected-row' : '')"
              :custom-row="(record: PocketRow) => ({ onClick: () => (selectedPocket = record.id) })"
            />
          </a-card>
          <a-card title="口袋空间位置（3D）" :bordered="false" class="panel-card viewer-card">
            <MoleculeViewer v-if="scene" :scene="scene" variant="full" />
            <div class="viewer-caption">高亮区域为 Top-1 口袋（Pocket-01）</div>
          </a-card>
        </section>
        <a-card title="关键口袋残基" :bordered="false" class="panel-card">
          <div class="residue-list">
            <a-tag v-for="res in pocketResidues" :key="res" color="blue">{{ res }}</a-tag>
          </div>
          <a-descriptions :column="3" size="small" bordered class="pocket-desc">
            <a-descriptions-item label="口袋体积">1284.6 Å³</a-descriptions-item>
            <a-descriptions-item label="疏水占比">62.4%</a-descriptions-item>
            <a-descriptions-item label="极性占比">37.6%</a-descriptions-item>
            <a-descriptions-item label="氢键供体位点">7</a-descriptions-item>
            <a-descriptions-item label="氢键受体位点">11</a-descriptions-item>
            <a-descriptions-item label="预测置信度">0.94</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-tab-pane>

      <a-tab-pane key="design" tab="AI 分子与多肽设计">
        <a-card title="小分子生成结果" :bordered="false" class="panel-card">
          <a-table
            :columns="moleculeColumns"
            :data-source="molecules"
            :pagination="false"
            size="small"
            :scroll="{ x: 1180 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'structure'">
                <Smiles2DCell :smiles="record.smiles" />
              </template>
              <template v-else-if="column.key === 'score'">
                <a-progress
                  :percent="Math.round(record.score * 100)"
                  size="small"
                  :stroke-color="record.score > 0.85 ? chartColors.positive : chartColors.primary"
                />
              </template>
              <template v-else-if="column.key === 'status'">
                <a-tag :color="record.status === '优选' ? 'green' : 'blue'">{{ record.status }}</a-tag>
              </template>
            </template>
          </a-table>
        </a-card>

        <a-card title="多肽序列设计样例" :bordered="false" class="panel-card">
          <div class="peptide-grid">
            <div v-for="peptide in peptides" :key="peptide.id" class="peptide-card">
              <div class="peptide-head">
                <span class="peptide-id">{{ peptide.id }}</span>
                <a-tag color="purple">结合能 {{ peptide.affinity }} kcal/mol</a-tag>
              </div>
              <div class="peptide-seq">{{ peptide.sequence }}</div>
              <div class="peptide-meta">
                <span>长度 {{ peptide.length }} aa</span>
                <span>螺旋度 {{ peptide.helix }}%</span>
                <span>溶解度 {{ peptide.solubility }}</span>
                <span>稳定性 {{ peptide.stability }}</span>
              </div>
            </div>
          </div>
        </a-card>
      </a-tab-pane>

      <a-tab-pane key="admet" tab="亲和力与 ADMET">
        <a-card title="亲和力与理化性质预测" :bordered="false" class="panel-card">
          <a-table
            :columns="admetColumns"
            :data-source="admetRows"
            :pagination="false"
            size="small"
          />
        </a-card>

        <section class="chart-grid">
          <a-card title="综合成药性雷达" :bordered="false" class="panel-card">
            <DemoChart :option="admetRadarOption" :height="320" />
          </a-card>
          <a-card title="Top 化合物关键指标" :bordered="false" class="panel-card">
            <DemoChart :option="admetBarOption" :height="320" />
          </a-card>
        </section>
      </a-tab-pane>

      <a-tab-pane key="screening" tab="虚拟筛选与计算评估">
        <section class="chart-grid">
          <a-card title="虚拟筛选漏斗" :bordered="false" class="panel-card">
            <DemoChart :option="funnelOption" :height="320" />
          </a-card>
          <a-card title="候选化合物排序" :bordered="false" class="panel-card">
            <DemoChart :option="rankBarOption" :height="320" />
          </a-card>
        </section>

        <a-card title="筛选排序表（Top 12）" :bordered="false" class="panel-card">
          <a-table
            :columns="screenColumns"
            :data-source="screenRows"
            :pagination="false"
            size="small"
            :scroll="{ x: 1080 }"
          />
        </a-card>

        <section class="chart-grid">
          <a-card title="分子动力学 · RMSD" :bordered="false" class="panel-card">
            <DemoChart :option="rmsdOption" :height="300" />
          </a-card>
          <a-card title="分子动力学 · RMSF" :bordered="false" class="panel-card">
            <DemoChart :option="rmsfOption" :height="300" />
          </a-card>
        </section>

        <a-card title="MM-PBSA 结合自由能分解" :bordered="false" class="panel-card">
          <DemoChart :option="freeEnergyOption" :height="320" />
          <a-descriptions :column="4" size="small" bordered class="energy-desc">
            <a-descriptions-item label="ΔG_bind">-42.86 kcal/mol</a-descriptions-item>
            <a-descriptions-item label="ΔE_vdW">-48.32 kcal/mol</a-descriptions-item>
            <a-descriptions-item label="ΔE_ele">-126.74 kcal/mol</a-descriptions-item>
            <a-descriptions-item label="ΔG_solv">118.45 kcal/mol</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { EChartsOption } from 'echarts'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import MoleculeViewer from '@/components/tasks/MoleculeViewer.vue'
import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
import type { VisualizationScene } from '@/domain/tasks'
import DemoChart from './DemoChart.vue'
import { chartColors, chartPalette } from '@/utils/chartTheme'

const activeTab = ref('structure')
const selectedPocket = ref('Pocket-01')
const pdbUrl = ref('')

const protein = {
  name: 'GRK4 激酶结构域（G 蛋白偶联受体激酶 4）',
  model: 'Boltz-2',
  sequence:
    'MELENIVANSLLLKARQGGYGKKSGRSKKWKEILTLPPVSQCSELRHSIEKDYSSLCDKQPIGRRLFRQFCDTKPTLKRHIEFLDAVAEYEVADDEDRSDCGLSILDRFFNDKLAAPLPEIPPDVVTECRLGLKEENPSKKAFEECTRVAHNYLRGEPFEEYQESSYFSQFLQWKWLERQPVTKNTFRHYRVLGKGGFGEVCACQVRATGKMYACKKLQKKRIKKRKGEAMALNEKRILEKVQSRFVVSLAYAYETKDALCLVLTIMNGGDLKFHIYNLGNPGFDEQRAVFYAAELCCGLEDLQRERIVYRDLKPENILLDDRGHIRISDLGLATEIPEGQRVRGRVGTVGYMAPEVVNNEKYTFSPDWWGLGCLIYEMIQGHSPFKKYKEKVKWEEVDQRIKNDTEEYSEKFSEDAKSICRMLLTKNPSKRLGCRGEGAAGVKQHPVFKDINFRRLEANMLEPPFCPDPHAVYCKDVLDIEQFSVVKGIYLDTADEDFYARFATGCVSIPWQNEMIESGCFKDINKSESEEALPLDLDKNIHTPVSRPNRGFFYRLFRRGGSLTMVPSEKEVEPKQSENLYFQ'
}

const summaryCards = [
  { label: '项目名称', value: 'GRK4 靶向高血压候选药物研发', hint: '心血管 / 激酶靶点' },
  { label: '评估化合物', value: '1,284,730', hint: '虚拟筛选库规模' },
  { label: '优选候选', value: '12', hint: '进入 MD / 自由能验证' },
  { label: '计算周期', value: '18 天', hint: '结构预测至自由能评估' }
]

const scene = computed<VisualizationScene | null>(() => {
  if (!pdbUrl.value) return null
  return {
    entries: [
      {
        key: 'grk4',
        url: pdbUrl.value,
        label: 'GRK4 kinase domain',
        source: 'output',
        role: 'structure',
        format: 'pdb',
        extension: '.pdb'
      }
    ],
    inputEntries: [],
    outputEntries: [],
    supportedOutputFiles: [],
    unsupportedOutputFiles: [],
    hasRenderableOutput: true,
    selectedOutputKey: 'grk4'
  }
})

interface PocketRow {
  id: string
  score: number
  druggability: number
  volume: number
  residueCount: number
  center: string
}
const pockets: PocketRow[] = [
  { id: 'Pocket-01', score: 0.94, druggability: 0.91, volume: 1284.6, residueCount: 24, center: '12.4, -8.7, 31.2' },
  { id: 'Pocket-02', score: 0.87, druggability: 0.84, volume: 946.2, residueCount: 19, center: '18.9, -2.1, 27.6' },
  { id: 'Pocket-03', score: 0.81, druggability: 0.79, volume: 812.4, residueCount: 17, center: '5.7, -14.3, 20.8' },
  { id: 'Pocket-04', score: 0.76, druggability: 0.72, volume: 704.8, residueCount: 15, center: '21.2, 4.6, 35.1' },
  { id: 'Pocket-05', score: 0.68, druggability: 0.65, volume: 588.3, residueCount: 12, center: '-3.4, -9.2, 24.5' }
]
const pocketColumns = [
  { title: '口袋编号', dataIndex: 'id', key: 'id' },
  { title: '综合评分', dataIndex: 'score', key: 'score' },
  { title: '成药性', dataIndex: 'druggability', key: 'druggability' },
  { title: '体积 (Å³)', dataIndex: 'volume', key: 'volume' },
  { title: '残基数', dataIndex: 'residueCount', key: 'residueCount' },
  { title: '中心坐标', dataIndex: 'center', key: 'center' }
]
const pocketResidues = ['Leu193', 'Val197', 'Ala201', 'Met204', 'Thr208', 'Phe212', 'Glu216', 'Arg220', 'Asn224', 'Leu228', 'Gly232', 'Asp236']

const moleculeColumns = [
  { title: '编号', dataIndex: 'id', key: 'id', width: 90 },
  { title: '结构式', key: 'structure', width: 170 },
  { title: 'SMILES', dataIndex: 'smiles', key: 'smiles', width: 320, ellipsis: true },
  { title: 'MW', dataIndex: 'mw', key: 'mw', width: 80 },
  { title: 'logP', dataIndex: 'logp', key: 'logp', width: 80 },
  { title: 'QED', dataIndex: 'qed', key: 'qed', width: 80 },
  { title: 'SA', dataIndex: 'sa', key: 'sa', width: 70 },
  { title: '生成评分', key: 'score', width: 140 },
  { title: '状态', key: 'status', width: 90 }
]
const molecules = [
  { key: '1', id: 'GEN-001', smiles: 'COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1', mw: 446.9, logp: 3.2, qed: 0.86, sa: 2.4, score: 0.94, status: '优选' },
  { key: '2', id: 'GEN-002', smiles: 'Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(n1)-c1cccnc1', mw: 493.6, logp: 2.8, qed: 0.82, sa: 2.8, score: 0.92, status: '优选' },
  { key: '3', id: 'GEN-003', smiles: 'COc1cc2ncnc(Nc3cccc(OCCO)c3)c2cc1OCCO', mw: 393.4, logp: 2.4, qed: 0.84, sa: 2.5, score: 0.9, status: '优选' },
  { key: '4', id: 'GEN-004', smiles: 'CNC(=O)c1cc(Oc2ccc(NC(=O)Nc3cc(C(F)(F)F)ccc3Cl)cc2)ccn1', mw: 464.8, logp: 3.6, qed: 0.79, sa: 3.1, score: 0.88, status: '优选' },
  { key: '5', id: 'GEN-005', smiles: 'Oc1cc(O)c2c(c1)oc(-c1ccc(O)c(O)c1)c(O)c2=O', mw: 302.2, logp: 1.5, qed: 0.71, sa: 2.2, score: 0.83, status: '备选' },
  { key: '6', id: 'GEN-006', smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O', mw: 206.3, logp: 3.5, qed: 0.77, sa: 1.8, score: 0.81, status: '备选' },
  { key: '7', id: 'GEN-007', smiles: 'CC(=O)Oc1ccccc1C(=O)O', mw: 180.2, logp: 1.2, qed: 0.68, sa: 1.3, score: 0.78, status: '备选' },
  { key: '8', id: 'GEN-008', smiles: 'Cn1cnc2c1c(=O)n(C)c(=O)n2C', mw: 194.2, logp: -0.1, qed: 0.64, sa: 1.6, score: 0.75, status: '备选' }
]

const peptides = [
  { id: 'PEP-01', sequence: 'Ac-DEETGEFLCKITV-OH', length: 13, affinity: '-11.8', helix: 72, solubility: '1.8 mg/mL', stability: '高' },
  { id: 'PEP-02', sequence: 'Ac-RRKLLERLKRLL-NH2', length: 13, affinity: '-10.6', helix: 84, solubility: '3.2 mg/mL', stability: '中' },
  { id: 'PEP-03', sequence: 'H-Cys-Tyr-Gly-Arg-Lys-Lys-Arg-Arg-Gln-Arg-Arg-Arg-OH', length: 12, affinity: '-9.9', helix: 46, solubility: '5.6 mg/mL', stability: '高' }
]

const admetColumns = [
  { title: '化合物', dataIndex: 'id', key: 'id', width: 95 },
  { title: '亲和力 (kcal/mol)', dataIndex: 'affinity', key: 'affinity', width: 130 },
  { title: 'MW', dataIndex: 'mw', key: 'mw', width: 75 },
  { title: 'logP', dataIndex: 'logp', key: 'logp', width: 70 },
  { title: 'QED', dataIndex: 'qed', key: 'qed', width: 70 },
  { title: 'hERG', dataIndex: 'herg', key: 'herg', width: 85 },
  { title: '半衰期 (h)', dataIndex: 'halfLife', key: 'halfLife', width: 100 },
  { title: 'Ames', dataIndex: 'ames', key: 'ames', width: 75 },
  { title: '溶解度 (mg/mL)', dataIndex: 'solubility', key: 'solubility', width: 120 },
  { title: '口服吸收 (%)', dataIndex: 'bioavailability', key: 'bioavailability', width: 115 }
]
const admetRows = [
  { key: '1', id: 'GEN-001', affinity: '-11.2', mw: 446.9, logp: 3.2, tpsa: 86.4, hbhba: '2 / 7', qed: 0.86, herg: '低风险', cyp: '弱抑制', clearance: '8.4', halfLife: '6.8', ames: '阴性', solubility: '0.42', bioavailability: '76.3' },
  { key: '2', id: 'GEN-002', affinity: '-10.8', mw: 493.6, logp: 2.8, tpsa: 94.2, hbhba: '3 / 8', qed: 0.82, herg: '中风险', cyp: '中等抑制', clearance: '11.2', halfLife: '5.2', ames: '阴性', solubility: '0.28', bioavailability: '68.5' },
  { key: '3', id: 'GEN-003', affinity: '-10.5', mw: 393.4, logp: 2.4, tpsa: 102.8, hbhba: '3 / 8', qed: 0.84, herg: '低风险', cyp: '弱抑制', clearance: '7.1', halfLife: '7.4', ames: '阴性', solubility: '0.65', bioavailability: '81.2' },
  { key: '4', id: 'GEN-004', affinity: '-10.1', mw: 464.8, logp: 3.6, tpsa: 88.1, hbhba: '2 / 7', qed: 0.79, herg: '中风险', cyp: '中等抑制', clearance: '13.6', halfLife: '4.6', ames: '阴性', solubility: '0.19', bioavailability: '61.7' },
  { key: '5', id: 'GEN-005', affinity: '-9.6', mw: 302.2, logp: 1.5, tpsa: 131.4, hbhba: '5 / 10', qed: 0.71, herg: '低风险', cyp: '弱抑制', clearance: '5.8', halfLife: '3.9', ames: '阴性', solubility: '1.20', bioavailability: '54.3' },
  { key: '6', id: 'GEN-006', affinity: '-9.2', mw: 206.3, logp: 3.5, tpsa: 37.3, hbhba: '1 / 2', qed: 0.77, herg: '低风险', cyp: '无抑制', clearance: '9.4', halfLife: '2.8', ames: '阴性', solubility: '0.88', bioavailability: '88.1' },
  { key: '7', id: 'GEN-007', affinity: '-8.7', mw: 180.2, logp: 1.2, tpsa: 63.6, hbhba: '1 / 4', qed: 0.68, herg: '低风险', cyp: '无抑制', clearance: '15.2', halfLife: '1.6', ames: '阴性', solubility: '2.40', bioavailability: '92.4' },
  { key: '8', id: 'GEN-008', affinity: '-8.1', mw: 194.2, logp: -0.1, tpsa: 58.4, hbhba: '0 / 6', qed: 0.64, herg: '低风险', cyp: '弱抑制', clearance: '4.6', halfLife: '4.2', ames: '阴性', solubility: '3.10', bioavailability: '96.7' }
]

const admetRadarOption: EChartsOption = {
  tooltip: {},
  radar: {
    indicator: [
      { name: '亲和力', max: 100 },
      { name: '成药性', max: 100 },
      { name: '吸收', max: 100 },
      { name: '安全性', max: 100 },
      { name: '溶解度', max: 100 },
      { name: '代谢稳定性', max: 100 }
    ],
    radius: '65%'
  },
  series: [
    {
      type: 'radar',
      data: [
        {
          value: [92, 88, 76, 86, 72, 81],
          name: 'GEN-001',
          areaStyle: { opacity: 0.25 },
          lineStyle: { width: 2 }
        },
        {
          value: [78, 74, 62, 70, 58, 66],
          name: 'GEN-004',
          areaStyle: { opacity: 0.12 },
          lineStyle: { width: 1.5, type: 'dashed' }
        }
      ]
    }
  ],
  legend: { bottom: 0 }
}

const admetBarOption: EChartsOption = {
  tooltip: { trigger: 'axis' },
  legend: { bottom: 0 },
  grid: { left: 50, right: 20, top: 20, bottom: 40 },
  xAxis: { type: 'category', data: admetRows.map(row => row.id) },
  yAxis: [{ type: 'value', name: 'QED' }],
  series: [
    {
      name: 'QED',
      type: 'bar',
      data: admetRows.map(row => row.qed),
      itemStyle: { color: chartColors.primary, borderRadius: [4, 4, 0, 0] }
    }
  ]
}

const funnelOption: EChartsOption = {
  tooltip: { trigger: 'item', formatter: '{b}: {c}' },
  color: [...chartPalette],
  series: [
    {
      type: 'funnel',
      left: '8%',
      right: '8%',
      top: 10,
      bottom: 10,
      sort: 'none',
      minSize: '28%',
      gap: 2,
      label: { position: 'inside', formatter: '{b}: {c}' },
      data: [
        { name: '化合物库', value: 1284730 },
        { name: '类药性过滤', value: 284610 },
        { name: '药效团匹配', value: 42870 },
        { name: '分子对接', value: 5120 },
        { name: 'ADMET 评估', value: 862 },
        { name: 'MD / 自由能验证', value: 12 }
      ]
    }
  ]
}

const topRows = screenRowsSeed()
const rankBarOption: EChartsOption = {
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 90, right: 30, top: 14, bottom: 30 },
  xAxis: { type: 'value', name: '对接评分' },
  yAxis: { type: 'category', data: topRows.slice(0, 8).map(row => row.id).reverse() },
  series: [
    {
      type: 'bar',
      data: topRows.slice(0, 8).map(row => row.docking).reverse(),
      itemStyle: { color: chartPalette[1], borderRadius: [0, 4, 4, 0] }
    }
  ]
}

const screenColumns = [
  { title: '排名', dataIndex: 'rank', key: 'rank', width: 70 },
  { title: '化合物', dataIndex: 'id', key: 'id', width: 100 },
  { title: '对接评分 (kcal/mol)', dataIndex: 'docking', key: 'docking', width: 150 },
  { title: 'MM-GBSA (kcal/mol)', dataIndex: 'mmgbsa', key: 'mmgbsa', width: 150 },
  { title: 'QED', dataIndex: 'qed', key: 'qed', width: 75 },
  { title: 'ADMET 通过', dataIndex: 'admet', key: 'admet', width: 110 },
  { title: '选择性指数', dataIndex: 'selectivity', key: 'selectivity', width: 110 },
  { title: '来源', dataIndex: 'source', key: 'source', width: 110 }
]

function screenRowsSeed() {
  const rows = [] as Array<{
    key: string
    rank: number
    id: string
    docking: number
    mmgbsa: number
    qed: number
    admet: string
    selectivity: number
    source: string
  }>
  for (let i = 0; i < 12; i += 1) {
    const base = -12.4 + i * 0.23 + (i % 3) * 0.05
    const mol = molecules[i]
    rows.push({
      key: String(i + 1),
      rank: i + 1,
      id: mol?.id ?? `SCR-${String(i + 1).padStart(3, '0')}`,
      docking: Number(base.toFixed(2)),
      mmgbsa: Number((base * 3.6 - 4.2).toFixed(2)),
      qed: mol?.qed ?? Number((0.66 - i * 0.01).toFixed(2)),
      admet: i < 5 ? '通过' : i < 9 ? '部分通过' : '复核',
      selectivity: Number((18.4 - i * 0.9).toFixed(1)),
      source: i % 2 === 0 ? '生成库' : '商业库'
    })
  }
  return rows
}

const screenRows = topRows

const rmsdOption: EChartsOption = {
  tooltip: { trigger: 'axis' },
  grid: { left: 50, right: 20, top: 24, bottom: 34 },
  xAxis: { type: 'category', name: '时间 (ns)', data: Array.from({ length: 21 }, (_, i) => i * 5) },
  yAxis: { type: 'value', name: 'RMSD (Å)', min: 0, max: 4 },
  series: [
    {
      type: 'line',
      smooth: true,
      symbol: 'none',
      data: [0.2, 0.8, 1.3, 1.6, 1.8, 1.9, 2.1, 2.0, 2.2, 2.1, 2.3, 2.2, 2.3, 2.4, 2.3, 2.4, 2.4, 2.5, 2.4, 2.5, 2.4],
      areaStyle: { opacity: 0.12 },
      lineStyle: { color: chartColors.primary, width: 2 }
    }
  ]
}

const rmsfOption: EChartsOption = {
  tooltip: { trigger: 'axis' },
  grid: { left: 50, right: 20, top: 24, bottom: 34 },
  xAxis: {
    type: 'category',
    name: '残基编号',
    data: Array.from({ length: 30 }, (_, i) => 20 + i * 20)
  },
  yAxis: { type: 'value', name: 'RMSF (Å)', min: 0, max: 3 },
  series: [
    {
      type: 'line',
      smooth: true,
      symbol: 'none',
      data: [0.4, 0.6, 0.5, 0.8, 1.1, 0.9, 0.7, 1.3, 1.8, 2.2, 1.7, 1.2, 0.9, 0.8, 1.1, 1.4, 1.9, 2.4, 1.8, 1.3, 0.9, 0.7, 0.8, 1.0, 1.3, 1.1, 0.9, 0.7, 0.6, 0.5],
      lineStyle: { color: chartColors.positive, width: 2 }
    }
  ]
}

const freeEnergyOption: EChartsOption = {
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 60, right: 20, top: 20, bottom: 40 },
  xAxis: { type: 'category', data: ['ΔE_vdW', 'ΔE_ele', 'ΔG_polar', 'ΔG_nonpolar', 'ΔG_bind'] },
  yAxis: { type: 'value', name: 'kcal/mol' },
  series: [
    {
      type: 'bar',
      data: [
        { value: -48.32, itemStyle: { color: chartColors.positive } },
        { value: -126.74, itemStyle: { color: chartColors.primary } },
        { value: 138.92, itemStyle: { color: chartColors.warning } },
        { value: -6.72, itemStyle: { color: chartPalette[4] } },
        { value: -42.86, itemStyle: { color: chartColors.negative } }
      ],
      label: { show: true, position: 'top', formatter: '{c}' },
      itemStyle: { borderRadius: [4, 4, 0, 0] }
    }
  ]
}

function notifyDone(text: string) {
  message.success(text)
}

onMounted(async () => {
  try {
    const response = await fetch('/demo/grk4.pdb')
    const text = await response.text()
    pdbUrl.value = URL.createObjectURL(new Blob([text], { type: 'chemical/x-pdb' }))
  } catch {
    pdbUrl.value = ''
  }
})

onBeforeUnmount(() => {
  if (pdbUrl.value) URL.revokeObjectURL(pdbUrl.value)
})
</script>

<style scoped lang="less">
.achievements-page {
  padding: 24px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 8px;
}
.summary-card {
  background: var(--color-bg-container);
  border: 1px solid var(--color-border-secondary);
  border-radius: 10px;
}
.summary-label {
  color: var(--color-text-secondary);
  font-size: 13px;
  margin-bottom: 8px;
}
.summary-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.3;
}
.summary-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.achievement-tabs {
  margin-top: 12px;
}
.panel-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.panel-card {
  background: var(--color-bg-container);
  border: 1px solid var(--color-border-secondary);
  border-radius: 10px;
  margin-bottom: 16px;
}
.viewer-card :deep(.ant-card-body) {
  padding: 0;
}
.viewer-card :deep(.molecule-viewer) {
  height: 420px;
  border-radius: 0 0 10px 10px;
}
.viewer-loading {
  height: 420px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-text-secondary);
}
.viewer-caption {
  padding: 8px 16px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  border-top: 1px solid var(--color-border-secondary);
}
.field-label {
  margin: 10px 0 6px;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.sequence-input :deep(textarea) {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.7;
}
.param-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.run-button {
  margin-top: 18px;
  width: 160px;
}
.selected-row {
  background: var(--theme-accent-light);
}
.residue-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.pocket-desc {
  margin-top: 8px;
}
.peptide-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.peptide-card {
  padding: 16px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 10px;
  background: var(--color-fill-quaternary);
}
.peptide-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.peptide-id {
  font-weight: 600;
  color: var(--color-text-primary);
}
.peptide-seq {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
  line-height: 1.8;
  word-break: break-all;
  color: var(--theme-accent);
  min-height: 72px;
}
.peptide-meta {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.energy-desc {
  margin-top: 8px;
}
@media (max-width: 1100px) {
  .summary-grid,
  .peptide-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .panel-grid,
  .chart-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
