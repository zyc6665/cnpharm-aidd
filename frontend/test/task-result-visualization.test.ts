import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  buildFocusedVisualizationScene,
  buildVisualizationScene
} from '../src/components/tasks/result-visualization.ts'
import {
  detectSdfScoreRankingFile,
  preferTopRankedSdfFiles,
  rankSdfEntriesByScore
} from '../src/components/tasks/sdf-ranking.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('任务结果可视化组件与规则模块应存在', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/ResultVisualizationPanel.vue')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/MoleculeViewer.vue')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/result-visualization.ts')), true)
})

test('任务详情页应接入结果可视化面板', () => {
  const detailSource = readSource('src/views/tasks/Detail.vue')
  const panelSource = readSource('src/components/tasks/ResultVisualizationPanel.vue')

  assert.equal(detailSource.includes('ResultVisualizationPanel'), true)
  assert.equal(panelSource.includes('result-visualization'), true)
})

test('结果可视化规则应覆盖首批结构与小分子格式', () => {
  const rulesSource = readSource('src/components/tasks/result-visualization.ts')

  assert.equal(rulesSource.includes('.pdb'), true)
  assert.equal(rulesSource.includes('.cif'), true)
  assert.equal(rulesSource.includes('.mmcif'), true)
  assert.equal(rulesSource.includes('.pdbqt'), true)
  assert.equal(rulesSource.includes('.sdf'), true)
  assert.equal(rulesSource.includes('.mol2'), true)
})

test('多输出三维结果应保留固定输入并支持逐项切换输出', () => {
  const scene = buildVisualizationScene({
    id: 'task-1',
    tool_id: 'tool-1',
    status: 'success',
    progress: 100,
    created_at: '2026-05-28T00:00:00Z',
    input_files: [
      {
        id: 'input-1',
        original_name: 'pocket.pdb',
        content_type: 'chemical/x-pdb',
        url: '/api/v1/files/input-1/download'
      }
    ],
    output_files: [
      {
        id: 'output-1',
        original_name: 'pose_1.sdf',
        content_type: 'chemical/x-mdl-sdfile',
        url: '/api/v1/files/output-1/download'
      },
      {
        id: 'output-2',
        original_name: 'pose_2.sdf',
        content_type: 'chemical/x-mdl-sdfile',
        url: '/api/v1/files/output-2/download'
      }
    ]
  })

  assert.equal(scene.inputEntries.length, 1)
  assert.equal(scene.outputEntries.length, 2)
  assert.equal(scene.selectedOutputKey, scene.outputEntries[0]?.key || null)
  assert.deepEqual(
    scene.entries.map(entry => entry.key),
    [scene.inputEntries[0]?.key, scene.outputEntries[0]?.key]
  )

  const switchedScene = buildFocusedVisualizationScene(scene, scene.outputEntries[1]?.key)

  assert.equal(switchedScene.selectedOutputKey, scene.outputEntries[1]?.key || null)
  assert.deepEqual(
    switchedScene.entries.map(entry => entry.key),
    [scene.inputEntries[0]?.key, scene.outputEntries[1]?.key]
  )
})

test('结果面板源码应包含输出结果列表选择逻辑', () => {
  const panelSource = readSource('src/components/tasks/ResultVisualizationPanel.vue')

  assert.equal(panelSource.includes('selectedOutputKey'), true)
  assert.equal(panelSource.includes('scene.outputEntries'), true)
})

test('结果可视化应修复内置全屏入口，而不是额外包一层自定义全屏弹层', () => {
  const panelSource = readSource('src/components/tasks/ResultVisualizationPanel.vue')
  const viewerSource = readSource('src/components/tasks/MoleculeViewer.vue')

  assert.equal(panelSource.includes('v-model:open="isFullscreen"'), false)
  assert.equal(panelSource.includes('FullscreenOutlined'), false)
  assert.equal(panelSource.includes('visualizationFullscreen'), false)

  assert.equal(viewerSource.includes('viewportShowToggleFullscreen: true'), true)
  assert.equal(viewerSource.includes('var(--viewer-height)'), false)
  assert.equal(viewerSource.includes('fullscreen?: boolean'), false)
  assert.equal(viewerSource.includes('height: 100%'), true)
  assert.equal(viewerSource.includes('msp-layout-expanded'), true)
  assert.equal(viewerSource.includes('expandToFullscreen && !layoutState.isExpanded'), true)
  assert.equal(viewerSource.includes('!layoutState.expandToFullscreen && layoutState.isExpanded'), true)
  assert.equal(viewerSource.includes('PluginCommands.Layout.Update'), true)
  assert.equal(viewerSource.includes('z-index: 1100'), true)
})

test('口袋受体应使用 polymer-cartoon 表示且不复用球棍默认视图', () => {
  const viewerSource = readSource('src/components/tasks/MoleculeViewer.vue')

  assert.equal(viewerSource.includes("entry.role === 'receptor'"), true)
  assert.equal(viewerSource.includes("representationPreset: 'polymer-cartoon'"), true)
  assert.equal(viewerSource.includes("plugin.builders.structure.hierarchy.applyPreset"), true)
})

test('带 QED 排名的 SDF 输出应按分数降序截取 Top 10', () => {
  const entries = Array.from({ length: 12 }, (_, index) => ({
    key: `output-${index}`,
    url: `/api/v1/files/${index}/download`,
    label: `artifacts__SDF__${index}.sdf`,
    source: 'output' as const,
    role: 'ligand' as const,
    format: 'sdf' as const,
    extension: '.sdf'
  }))
  const csvText = [
    'index,smiles,sdf_file,qed',
    '0,CCO,SDF/0.sdf,0.12',
    '1,CCN,SDF/1.sdf,0.81',
    '2,CCC,SDF/2.sdf,0.55',
    '3,CCCl,SDF/3.sdf,0.44',
    '4,CCBr,SDF/4.sdf,0.91',
    '5,COC,SDF/5.sdf,0.31',
    '6,CNC,SDF/6.sdf,0.72',
    '7,CSC,SDF/7.sdf,0.63',
    '8,CFC,SDF/8.sdf,0.22',
    '9,CIC,SDF/9.sdf,0.66',
    '10,c1ccccc1,SDF/10.sdf,0.76',
    '11,c1ccncc1,SDF/11.sdf,0.69'
  ].join('\n')

  const rankedEntries = rankSdfEntriesByScore(entries, csvText)

  assert.equal(rankedEntries.length, 10)
  assert.equal(rankedEntries[0]?.label, 'artifacts__SDF__4.sdf')
  assert.equal(rankedEntries[0]?.scoreLabel, 'QED 0.910')
  assert.deepEqual(
    rankedEntries.map(entry => entry.key),
    ['output-4', 'output-1', 'output-10', 'output-6', 'output-11', 'output-9', 'output-7', 'output-2', 'output-3', 'output-5']
  )
})

test('合并 SDF 展开后应能通过 CSV 原始 index 继续匹配 QED 排名', () => {
  const entries = Array.from({ length: 12 }, (_, index) => ({
    key: `combined::${index + 1}`,
    url: `blob:record-${index + 1}`,
    label: `generated_molecules.sdf #${index + 1}`,
    source: 'output' as const,
    role: 'ligand' as const,
    format: 'sdf' as const,
    extension: '.sdf',
    sdfRecordIndex: index
  }))
  const csvText = [
    'rank,index,smiles,sdf_file,qed',
    '1,10,c1ccccc1,SDF/62.sdf,0.93',
    '2,3,CCN,SDF/45.sdf,0.91',
    '3,0,CCO,SDF/4.sdf,0.82'
  ].join('\n')

  const rankedEntries = rankSdfEntriesByScore(entries, csvText)

  assert.equal(rankedEntries.length, 3)
  assert.equal(rankedEntries[0]?.label, 'generated_molecules.sdf #11')
  assert.equal(rankedEntries[0]?.scoreLabel, 'QED 0.930')
  assert.deepEqual(
    rankedEntries.map(entry => entry.key),
    ['combined::11', 'combined::4', 'combined::1']
  )
})

test('正式分子评分 CSV 应按 composite_score 展示 Top 10 标签', () => {
  const entries = Array.from({ length: 3 }, (_, index) => ({
    key: `combined::${index + 1}`,
    url: `blob:record-${index + 1}`,
    label: `generated_molecules.sdf #${index + 1}`,
    source: 'output' as const,
    role: 'ligand' as const,
    format: 'sdf' as const,
    extension: '.sdf',
    sdfRecordIndex: index
  }))
  const csvText = [
    'rank,index,smiles,sdf_file,qed,sa,vina_score,composite_score,error',
    '1,1,C1,generated_molecules_1.sdf,0.91,2.1,-8.2,0.88,',
    '2,2,C2,generated_molecules_2.sdf,0.72,3.4,-7.1,0.76,',
    '3,0,C0,generated_molecules_0.sdf,0.22,5.0,,0.31,'
  ].join('\n')

  const rankedEntries = rankSdfEntriesByScore(entries, csvText)

  assert.deepEqual(
    rankedEntries.map(entry => entry.key),
    ['combined::2', 'combined::3', 'combined::1']
  )
  assert.equal(rankedEntries[0]?.scoreLabel, 'Score 0.880')
})

test('结果可视化应优先使用后端生成的 top10_molecules.sdf', () => {
  const files = [
    {
      id: 'all',
      original_name: 'generated_molecules.sdf',
      content_type: 'chemical/x-mdl-sdfile',
      url: '/api/v1/files/all/download'
    },
    {
      id: 'score',
      original_name: 'molecule_scores.csv',
      content_type: 'text/csv',
      url: '/api/v1/files/score/download'
    },
    {
      id: 'top10',
      original_name: 'top10_molecules.sdf',
      content_type: 'chemical/x-mdl-sdfile',
      url: '/api/v1/files/top10/download'
    }
  ]

  assert.equal(detectSdfScoreRankingFile(files[1]), files[1])
  assert.deepEqual(preferTopRankedSdfFiles(files).map(file => file.id), ['top10'])
})
