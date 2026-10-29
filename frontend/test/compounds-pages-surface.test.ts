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

test('项目导航的 assets / results 项紧接在 tasks 之后且不影响既有 active 判定', async () => {
  const { buildProjectWorkspaceNavItems, isProjectWorkspaceNavItemActive } = await import(
    '../src/domain/projects/navigation'
  )
  const items = buildProjectWorkspaceNavItems('project-1')
  const keys = items.map(item => item.key)

  // targets 由 PR3 加入（锚点：overview 之后、workflow 之前），此处只断言本 PR 新增的两项相对位置。
  // decisions 由 P-39 决策记录页加入（锚点：results 之后、lineage 之前），因此需补进本清单。
  assert.deepEqual(keys, [
    'overview',
    'targets',
    'workflow',
    'tasks',
    'assets',
    'candidates',
    'results',
    'decisions',
    'lineage',
    'settings'
  ])
  assert.equal(keys.indexOf('assets'), keys.indexOf('tasks') + 1)
  assert.equal(keys.indexOf('overview'), 0)

  const assets = items.find(item => item.key === 'assets')
  assert.ok(assets, '缺少 assets 导航项')
  assert.equal(assets?.label, '数据资产')
  assert.equal(assets?.to, '/projects/project-1/assets')

  assert.equal(
    isProjectWorkspaceNavItemActive(assets!, {
      currentPath: '/projects/project-1/assets',
      currentProjectId: 'project-1'
    }),
    true
  )
  assert.equal(
    isProjectWorkspaceNavItemActive(assets!, {
      currentPath: '/projects/project-1/lineage',
      currentProjectId: 'project-1'
    }),
    false
  )

  // P-33 结果中心必须从项目导航可达（assets 之后、lineage 之前）
  const results = items.find(item => item.key === 'results')
  assert.ok(results, '缺少 results 导航项')
  assert.equal(results?.label, '结果中心')
  assert.equal(results?.to, '/projects/project-1/results')
  // P-12 之后候选物从资产页签移出、在导航中以独立入口紧随 assets；结果中心仍在 lineage 之前。
  assert.equal(keys.indexOf('candidates'), keys.indexOf('assets') + 1)
  assert.equal(keys.indexOf('results'), keys.indexOf('candidates') + 1)
  // P-39 在 results 与 lineage 之间插入了 decisions，results 的直接后继因此不再是 lineage。
  assert.equal(keys.indexOf('decisions'), keys.indexOf('results') + 1)
  assert.equal(keys.indexOf('decisions') + 1, keys.indexOf('lineage'))
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

test('Assets.vue 提供批量导入入口并展示导入汇总', () => {
  const source = readSource('src/views/compounds/Assets.vue')

  assert.ok(source.includes('importCompounds'), 'Assets.vue 必须调用 importCompounds')
  assert.ok(source.includes('uploadFile'), 'Assets.vue 必须先用 files/upload 拿 file_id')
  assert.ok(source.includes('.smi') && source.includes('.csv') && source.includes('.sdf'))
  assert.ok(source.includes('duplicate'), 'Assets.vue 需要展示 duplicate 统计')
})

test('数据资产页 Tab 为 化合物/蛋白/数据集，候选物移到独立页面', () => {
  const assets = readSource('src/views/compounds/Assets.vue')

  assert.ok(assets.includes('key="compounds"'), 'Assets.vue 缺少化合物 Tab')
  assert.ok(assets.includes('key="proteins"'), 'Assets.vue 缺少蛋白 Tab')
  assert.ok(assets.includes('key="datasets"'), 'Assets.vue 缺少数据集 Tab')
  assert.equal(assets.includes('key="candidates"'), false, 'Assets.vue 不应再含候选物 Tab')
  assert.equal(
    assets.includes('key="candidateSets"'),
    false,
    'Assets.vue 不应再含候选集 Tab'
  )
  // 蛋白 Tab 必须说明「只含 Artifact 结构产物，蛋白主数据在靶点与结构」。
  assert.ok(assets.includes('compounds.notes.proteins'), '蛋白 Tab 缺少语义说明')
  // 候选物必须有等价入口，不能成孤儿页面。
  assert.ok(assets.includes('/candidates'), 'Assets.vue 缺少候选物入口链接')
  assert.ok(assets.includes('listProjectAssets'), 'Assets.vue 必须调用统一资产接口')
  // 数据集 Tab 里 artifact_type='dataset' 的上传产物要区别于登记数据集。
  assert.ok(
    assets.includes('compounds.datasetSource.upload'),
    'Assets.vue 数据集 Tab 缺少「上传文件」来源标记'
  )

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

test('七个页面源码不含 any 类型逃逸', () => {
  for (const viewFile of VIEW_FILES) {
    const source = readSource(viewFile)
    assert.equal(/\bany\b/.test(source), false, `${viewFile} 出现 any`)
    assert.equal(/console\.log/.test(source), false, `${viewFile} 出现 console.log`)
    assert.equal(/https?:\/\//.test(source), false, `${viewFile} 出现公网地址`)
  }
})
