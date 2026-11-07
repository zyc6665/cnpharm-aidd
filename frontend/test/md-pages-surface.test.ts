import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  buildAnalysisRows,
  buildFreeEnergyRows,
  cumulativeMean,
  downsampleSeries,
  energyComponentMeans,
  estimateMdRuntimeHours,
  findOutputByStandardType,
  rowsToCsv,
  summarizeDeltaG
} from '@/views/md/analysis'
import type { FreeEnergyRow } from '@/types/md'
import type { ResultOutputArtifact } from '@/types/compounds'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

const VIEWS = [
  'src/views/md/MdSubmit.vue',
  'src/views/md/MdResult.vue',
  'src/views/md/FreeEnergyResult.vue',
  'src/views/md/analysis.ts',
  'src/views/md/MdEchart.vue',
  'src/api/md.ts',
  'src/types/md.ts'
]

test('MD 三页相关文件均已创建且视图使用 script setup lang="ts" + data-testid', () => {
  for (const file of VIEWS) {
    assert.ok(existsSync(resolve(rootDir, file)), `missing file: ${file}`)
  }
  for (const view of ['src/views/md/MdSubmit.vue', 'src/views/md/MdResult.vue', 'src/views/md/FreeEnergyResult.vue']) {
    const source = readSource(view)
    assert.ok(source.includes('<script setup lang="ts">'), `${view} 缺少 script setup lang="ts"`)
    assert.ok(source.includes('data-testid'), `${view} 缺少 data-testid`)
  }
})

test('router 注册三条 MD/自由能路由，路径与契约一致', () => {
  const routerSource = readSource('src/router/index.ts')

  const routes: Array<[string, string, string]> = [
    ['MdSubmit', '/md', '@/views/md/MdSubmit.vue'],
    ['MdResult', '/tasks/:id/md', '@/views/md/MdResult.vue'],
    ['FreeEnergyResult', '/tasks/:id/free-energy', '@/views/md/FreeEnergyResult.vue']
  ]

  for (const [name, path, view] of routes) {
    assert.ok(routerSource.includes(`name: '${name}'`), `router 缺少路由名 ${name}`)
    assert.ok(routerSource.includes(`path: '${path}'`), `router 缺少路径 ${path}`)
    assert.ok(routerSource.includes(`import('${view}')`), `router 未懒加载 ${view}`)
  }
})

test('api/md.ts 的 tool slug 与冻结契约一致', () => {
  const apiSource = readSource('src/api/md.ts')
  assert.ok(apiSource.includes("MD_TOOL_SLUG = 'gromacs-md'"), 'MD_TOOL_SLUG 不符')
  assert.ok(apiSource.includes("FREE_ENERGY_TOOL_SLUG = 'gmx-mmpbsa'"), 'FREE_ENERGY_TOOL_SLUG 不符')
  assert.ok(apiSource.includes("MD_TRAJECTORY_STANDARD_TYPE = 'md_trajectory@1'"), 'md_trajectory 标准类型不符')
  assert.ok(apiSource.includes("MOLECULE_TABLE_STANDARD_TYPE = 'molecule_table@1'"), 'molecule_table 标准类型不符')
})

test('MdSubmit 参数由 gromacs-md 模型 schema 动态渲染', () => {
  const source = readSource('src/views/md/MdSubmit.vue')
  assert.ok(source.includes('ModelParameterForm'), 'MdSubmit 未使用模型参数表单')
  assert.ok(source.includes('selectedOption?.parameterSchema'), 'MdSubmit 未读取模型参数 schema')
  assert.ok(source.includes('MD_TOOL_SLUG'), 'MdSubmit 未引用 MD_TOOL_SLUG')
  assert.ok(source.includes('estimateMdRuntimeHours'), 'MdSubmit 未使用耗时估算')
})

test('逐帧 ΔG 的均值、标准差与标准误真实计算', () => {
  const summary = summarizeDeltaG([-10, -12, -11, -9])
  assert.equal(summary.frameCount, 4)
  assert.ok(Math.abs(summary.mean - -10.5) < 1e-9, `mean=${summary.mean}`)
  // 样本标准差 (n-1)
  const expectedStd = Math.sqrt(5 / 3)
  assert.ok(Math.abs(summary.stdDev - expectedStd) < 1e-9, `stdDev=${summary.stdDev}`)
  assert.ok(Math.abs(summary.standardError - expectedStd / 2) < 1e-9, `se=${summary.standardError}`)

  const withNull = summarizeDeltaG([-10, null, -12, -11, -9])
  assert.equal(withNull.frameCount, 4, '应忽略缺失值')

  const empty = summarizeDeltaG([])
  assert.equal(empty.frameCount, 0)
  assert.ok(Number.isNaN(empty.mean))
})

test('累计均值（收敛曲线）与缺失值处理', () => {
  assert.deepEqual(cumulativeMean([-10, -20]), [-10, -15])
  const withNull = cumulativeMean([10, null, 20])
  assert.deepEqual(withNull, [10, 10, 15])
})

test('曲线抽样保留首尾并限制点数', () => {
  const items = Array.from({ length: 100 }, (_, index) => index)
  const sampled = downsampleSeries(items, 10)
  assert.equal(sampled.length, 10)
  assert.equal(sampled[0], 0)
  assert.equal(sampled[sampled.length - 1], 99)
  // 少于上限时原样返回
  assert.deepEqual(downsampleSeries([1, 2, 3], 10), [1, 2, 3])
})

test('能量分解各组分的均值真实计算', () => {
  const rows: FreeEnergyRow[] = [
    {
      frame: 1,
      delta_g_total: -30,
      delta_g_vdw: -40,
      delta_g_electrostatic: -10,
      delta_g_polar_solvation: 25,
      delta_g_nonpolar_solvation: -5,
      delta_g_sasa: -2
    },
    {
      frame: 2,
      delta_g_total: -20,
      delta_g_vdw: -30,
      delta_g_electrostatic: -20,
      delta_g_polar_solvation: 35,
      delta_g_nonpolar_solvation: -3,
      delta_g_sasa: -4
    }
  ]
  const means = energyComponentMeans(rows)
  assert.equal(means.length, 5)
  const vdw = means.find((item) => item.key === 'delta_g_vdw')
  assert.ok(vdw && Math.abs(vdw.mean - -35) < 1e-9, 'vdw 均值应为 -35')
  const polar = means.find((item) => item.key === 'delta_g_polar_solvation')
  assert.ok(polar && Math.abs(polar.mean - 30) < 1e-9, 'polar solvation 均值应为 30')
})

test('CSV 导出按列顺序生成并转义逗号/引号', () => {
  const csv = rowsToCsv(
    [{ frame: 1, delta_g_total: -30.5 }, { frame: 2, delta_g_total: -20 }],
    ['frame', 'delta_g_total']
  )
  assert.equal(csv.split('\n')[0], 'frame,delta_g_total')
  assert.ok(csv.includes('1,-30.5'))

  const escaped = rowsToCsv([{ note: 'a,b"c' }], ['note'])
  assert.ok(escaped.includes('"a,b""c"'), `转义失败: ${escaped}`)
})

test('MD 耗时粗估按 duration/(gpuCount*nsPerDay)*24 计算', () => {
  assert.equal(estimateMdRuntimeHours({ durationNs: 100, gpuCount: 1 }), 120)
  assert.equal(estimateMdRuntimeHours({ durationNs: 100, gpuCount: 4 }), 30)
  assert.ok(Number.isNaN(estimateMdRuntimeHours({ durationNs: 0, gpuCount: 1 })))
})

test('CSV 行解析：缺失 time_ps 的分析行被跳过，frame 缺失按行号兜底', () => {
  const analysis = buildAnalysisRows([
    { time_ps: '0', rmsd_nm: '0.1', rmsf_nm: '0.2', rg_nm: '1.5', temperature_k: '300', potential_kj_mol: '-1e5' },
    { time_ps: '', rmsd_nm: '0.2' }
  ])
  assert.equal(analysis.length, 1)
  assert.equal(analysis[0]?.rmsd_nm, 0.1)
  assert.equal(analysis[0]?.temperature_k, 300)

  const energyRows = buildFreeEnergyRows([{ delta_g_total: '-10' }, { frame: '5', delta_g_total: '-20' }])
  assert.equal(energyRows[0]?.frame, 1)
  assert.equal(energyRows[1]?.frame, 5)
})

test('findOutputByStandardType 支持精确与版本前缀匹配', () => {
  const outputs = [
    { id: 'a', semantic_type: 'trajectory', standard_type: 'md_trajectory@1' },
    { id: 'b', semantic_type: 'energies', standard_type: null }
  ] as unknown as ResultOutputArtifact[]
  assert.equal(findOutputByStandardType(outputs, 'md_trajectory@1')?.id, 'a')
  assert.equal(findOutputByStandardType(outputs, 'md_trajectory')?.id, 'a')
  assert.equal(findOutputByStandardType(outputs, 'molecule_table@1'), null)
})

test('两份语言包都新增了 md 命名空间（submit/result/freeEnergy）', () => {
  for (const locale of ['src/locales/zh-CN/index.ts', 'src/locales/en-US/index.ts']) {
    const source = readSource(locale)
    assert.ok(/^ {2}md: \{/m.test(source), `${locale} 缺少 md 命名空间`)
    assert.ok(source.includes('freeEnergy: {'), `${locale} 缺少 md.freeEnergy`)
    // 关键锚点
    for (const anchor of ['decompositionTitle', 'convergenceTitle', 'standardError']) {
      assert.ok(source.includes(anchor), `${locale} 缺少 md 键 ${anchor}`)
    }
  }
})
