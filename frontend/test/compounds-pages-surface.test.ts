import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

const VIEW_FILES = [
  'src/views/compounds/Assets.vue',
  'src/views/compounds/Candidates.vue',
  'src/views/compounds/CompoundDetail.vue',
  'src/views/compounds/CandidateSetDetail.vue',
  'src/views/compounds/CandidateDetail.vue',
  'src/views/compounds/Compare.vue',
  'src/views/results/List.vue',
  'src/views/results/ResultDetail.vue'
]

const ROUTE_NAMES = [
  'ProjectAssets',
  'ProjectCandidates',
  'CompoundDetail',
  'CandidateSetDetail',
  'CandidateDetail',
  'CandidateCompare',
  'ProjectResults',
  'ResultDetail'
]

test('七个化合物/候选物/结果视图文件均已创建', () => {
  for (const viewFile of VIEW_FILES) {
    assert.ok(existsSync(resolve(rootDir, viewFile)), `missing view: ${viewFile}`)
    const source = readSource(viewFile)
    assert.ok(source.includes('<script setup lang="ts">'), `${viewFile} 缺少 script setup lang="ts"`)
    assert.ok(source.includes('data-testid'), `${viewFile} 缺少 data-testid`)
  }
})

test('router 在 WorkflowRunDetail 之后注册 7 条新路由', () => {
  const routerSource = readSource('src/router/index.ts')
  const anchorIndex = routerSource.indexOf("name: 'WorkflowRunDetail'")
  assert.ok(anchorIndex >= 0, 'router 缺少 WorkflowRunDetail 路由')

  let previousIndex = anchorIndex
  for (const routeName of ROUTE_NAMES) {
    const routeIndex = routerSource.indexOf(`name: '${routeName}'`)
    assert.ok(routeIndex > anchorIndex, `${routeName} 必须插在 WorkflowRunDetail 之后`)
    assert.ok(routeIndex > previousIndex, `${routeName} 注册顺序不符合预期`)
    previousIndex = routeIndex
  }

  assert.ok(routerSource.includes('path: \'/projects/:projectId/assets\''))
  assert.ok(routerSource.includes('path: \'/projects/:projectId/candidates\''))
  assert.ok(routerSource.includes('path: \'/compounds/:compoundId\''))
  assert.ok(routerSource.includes('path: \'/candidate-sets/:setId\''))
  assert.ok(routerSource.includes('path: \'/candidates/:candidateId\''))
  assert.ok(routerSource.includes('path: \'/projects/:projectId/candidates/compare\''))
  assert.ok(routerSource.includes('path: \'/projects/:projectId/results\''))
  assert.ok(routerSource.includes('path: \'/results/:taskId\''))
})

test('项目导航的 assets / candidates 项紧接在 tasks 之后且覆盖合并后的子视图', async () => {
  const {
    buildProjectCandidateViewTabs,
    buildProjectDataViewTabs,
    buildProjectWorkspaceNavItems,
    isProjectWorkspaceNavItemActive
  } = await import('../src/domain/projects/navigation')
  const items = buildProjectWorkspaceNavItems('project-1')
  const keys = items.map(item => item.key)

  assert.deepEqual(keys, [
    'overview',
    'design',
    'workflow',
    'tasks',
    'assets',
    'candidates',
    'settings'
  ])
  assert.equal(keys.indexOf('assets'), keys.indexOf('tasks') + 1)
  assert.equal(keys.indexOf('candidates'), keys.indexOf('assets') + 1)
  assert.equal(keys.indexOf('overview'), 0)

  const assets = items.find(item => item.key === 'assets')
  assert.ok(assets, '缺少 assets 导航项')
  assert.equal(assets?.label, '数据与产物')
  assert.equal(assets?.to, '/projects/project-1/assets')

  // 数据资产、结果中心、Artifact 谱系三个视图合在「数据与产物」下，通过二级视图切换可达。
  for (const path of [
    '/projects/project-1/assets',
    '/projects/project-1/results',
    '/projects/project-1/lineage'
  ]) {
    assert.equal(
      isProjectWorkspaceNavItemActive(assets!, {
        currentPath: path,
        currentProjectId: 'project-1'
      }),
      true
    )
  }
  assert.deepEqual(
    buildProjectDataViewTabs('project-1').map(tab => tab.to),
    [
      '/projects/project-1/assets',
      '/projects/project-1/results',
      '/projects/project-1/lineage'
    ]
  )
  assert.deepEqual(
    buildProjectCandidateViewTabs('project-1').map(tab => tab.to),
    [
      '/projects/project-1/candidates',
      '/projects/project-1/decisions'
    ]
  )
})

test('i18n 中英双语均补齐 compounds / candidates / results 三个命名空间', () => {
  for (const localePath of ['src/locales/zh-CN/index.ts', 'src/locales/en-US/index.ts']) {
    const source = readSource(localePath)
    for (const namespace of ['compounds', 'candidates', 'results']) {
      assert.ok(
        source.includes(`  ${namespace}: {`),
        `${localePath} 缺少顶层命名空间 ${namespace}`
      )
    }
    assert.ok(source.includes('properties: {'), `${localePath} 缺少 properties 子命名空间`)
    assert.ok(source.includes('traceability: {'), `${localePath} 缺少 traceability 子命名空间`)
  }
})

test('Compare.vue 通过 domain 上限常量限制最多 6 个候选物', () => {
  const source = readSource('src/views/compounds/Compare.vue')

  assert.ok(source.includes('MAX_COMPARE_CANDIDATES'), 'Compare.vue 必须引用 MAX_COMPARE_CANDIDATES')
  assert.ok(source.includes('buildComparisonMatrix'), 'Compare.vue 必须使用 buildComparisonMatrix')
  assert.ok(source.includes('exportCsv') || source.includes('downloadCsv'), 'Compare.vue 需要 CSV 导出')
})

test('ResultDetail.vue 复用 getTraceability 并提供导出追溯包入口', () => {
  const source = readSource('src/views/results/ResultDetail.vue')

  assert.ok(source.includes('getTraceability'), 'ResultDetail.vue 必须调用 getTraceability')
  assert.ok(source.includes('exportTraceability'), 'ResultDetail.vue 必须提供导出追溯包')
  assert.ok(source.includes('traceability.'), 'ResultDetail.vue 必须渲染追溯包分区文案')
  assert.ok(!source.includes('components/traceability'), '不得新建第二个追溯组件')
})

test('Assets.vue 收敛为项目 Artifact 数据空间（按调用分组上传与下载）', () => {
  const source = readSource('src/views/compounds/Assets.vue')

  assert.ok(source.includes('uploadProjectArtifact'), 'Assets.vue 必须调用 uploadProjectArtifact')
  assert.ok(source.includes('getAllProjectArtifacts'), 'Assets.vue 必须加载项目 Artifact 数据空间')
  assert.ok(source.includes('artifactGroups'), 'Assets.vue 必须按工具调用分组展示数据空间')
})

test('数据资产页收敛为按调用目录分组的数据空间，候选物在独立页面', () => {
  const assets = readSource('src/views/compounds/Assets.vue')

  assert.ok(assets.includes('data-testid="assets-space-section"'), 'Assets.vue 缺少数据空间主视图')
  assert.equal(assets.includes('key="compounds"'), false, 'Assets.vue 不应再含平铺单分子 Tab')
  assert.equal(assets.includes('key="proteins"'), false, 'Assets.vue 不应再含重复的蛋白 Tab')
  assert.equal(assets.includes('key="datasets"'), false, 'Assets.vue 不应再含重复的数据集 Tab')
  assert.equal(assets.includes('key="candidates"'), false, 'Assets.vue 不应再含候选物 Tab')
  assert.equal(
    assets.includes('key="candidateSets"'),
    false,
    'Assets.vue 不应再含候选集 Tab'
  )
  assert.ok(assets.includes('artifactGroups'), 'Assets.vue 必须按工具调用分组展示数据空间')

  const candidates = readSource('src/views/compounds/Candidates.vue')
  assert.ok(candidates.includes('listCandidates'), 'Candidates.vue 必须列出候选物')
  assert.ok(candidates.includes('listCandidateSets'), 'Candidates.vue 必须列出候选集')
  assert.ok(candidates.includes('data-testid'), 'Candidates.vue 缺少 data-testid')
})

test('i18n 中英双语补齐数据资产新增 Tab 与候选物页面文案', () => {
  for (const localePath of ['src/locales/zh-CN/index.ts', 'src/locales/en-US/index.ts']) {
    const source = readSource(localePath)
    for (const key of [
      'proteinColumns:',
      'datasetColumns:',
      'datasetSource:',
      'notes:',
      'candidatesPage:',
      'loadAssets:'
    ]) {
      assert.ok(source.includes(key), `${localePath} 缺少 ${key}`)
    }
  }
})

test('CandidateSetDetail.vue 支持成员增删与导出', () => {
  const source = readSource('src/views/compounds/CandidateSetDetail.vue')

  assert.ok(source.includes('exportCandidateSet'), 'CandidateSetDetail.vue 必须调用 exportCandidateSet')
  assert.ok(source.includes('addCandidateSetItems'), 'CandidateSetDetail.vue 必须支持添加成员')
  assert.ok(source.includes('removeCandidateSetItem'), 'CandidateSetDetail.vue 必须支持移除成员')
  assert.ok(source.includes('currentVersion'), 'CandidateSetDetail.vue 需要展示乐观锁冲突的 currentVersion')
  assert.ok(source.includes('snapshot_score'), 'CandidateSetDetail.vue 需要展示 snapshot_score')
})

test('CandidateDetail.vue shows the results related to the candidate', () => {
  // docs/26 H-14: the page used to link a single task id, so users could not
  // tell how many runs involved the candidate or whether they succeeded.
  const viewSource = readSource('src/views/compounds/CandidateDetail.vue')
  assert.ok(
    viewSource.includes('listCandidateResults'),
    'CandidateDetail.vue must call listCandidateResults'
  )
  assert.ok(
    viewSource.includes('data-testid="candidate-result-table"'),
    'CandidateDetail.vue needs a related-result table'
  )
  assert.ok(
    viewSource.includes('data-testid="candidate-no-results"'),
    'CandidateDetail.vue needs an empty state for candidates without results'
  )

  const apiSource = readSource('src/api/results.ts')
  assert.ok(
    apiSource.includes('/candidates/${candidateId}/results'),
    'api/results.ts must request /candidates/{id}/results'
  )

  for (const localePath of ['src/locales/zh-CN/index.ts', 'src/locales/en-US/index.ts']) {
    const localeSource = readSource(localePath)
    for (const key of ['relatedResults:', 'noRelatedResults:', 'resultColumns:']) {
      assert.ok(localeSource.includes(key), `${localePath} is missing ${key}`)
    }
  }
})

test('七个页面源码不含 any 类型逃逸', () => {
  for (const viewFile of VIEW_FILES) {
    const source = readSource(viewFile)
    assert.equal(/\bany\b/.test(source), false, `${viewFile} 出现 any`)
    assert.equal(/console\.log/.test(source), false, `${viewFile} 出现 console.log`)
    assert.equal(/https?:\/\//.test(source), false, `${viewFile} 出现公网地址`)
  }
})
