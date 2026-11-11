import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  RESIDUE_PROPERTIES,
  residueCategoryColor,
  residuePropertyOf
} from '../src/domain/targets/residue-property'

/**
 * 口袋残基面板的回归网：多选、可缩放、关键残基与全部残基分层。
 *
 * 背景三条用户反馈：
 *   1. 关键残基只能单选，看不了「这几个残基一起围成的口袋」；
 *   2. 3D 画面滚轮与拖拽完全没反应——根因是给 Mol* 的 focusSphere 传了普通对象
 *      `{ center, radius }` 而不是 `Sphere3D`，相机状态被写成 NaN，之后任何交互
 *      都在 NaN 上算，看起来就是「卡死」；
 *   3. 99 个残基连着分数一起铺开，等于没有结论。关键残基要单列在上，
 *      全部残基放下面备查、不列分数。
 */

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('20 种标准氨基酸都有中文名、类别与疏水指数', () => {
  const codes = Object.keys(RESIDUE_PROPERTIES)
  assert.equal(codes.length, 20)
  for (const code of codes) {
    const property = RESIDUE_PROPERTIES[code]
    assert.ok(property, code)
    assert.equal(property.code, code)
    assert.ok(property.chinese.length >= 2, code)
    assert.ok(
      ['疏水', '芳香', '极性', '酸性', '碱性', '特殊'].includes(property.category),
      `${code} 类别非法: ${property.category}`
    )
    assert.equal(typeof property.hydropathy, 'number')
  }
})

test('未知残基返回占位而不是抛错，大小写不敏感', () => {
  const upper = residuePropertyOf('LEU')
  const lower = residuePropertyOf('leu')
  assert.equal(upper.chinese, '亮氨酸')
  assert.equal(lower.chinese, upper.chinese)
  assert.equal(upper.category, '疏水')

  const unknown = residuePropertyOf('XYZ')
  assert.equal(unknown.chinese, '未知残基')
  assert.equal(unknown.category, '特殊')

  const empty = residuePropertyOf(null)
  assert.equal(empty.chinese, '未知残基')
})

test('六类残基颜色互不相同，便于在表里区分', () => {
  const categories = ['疏水', '芳香', '极性', '酸性', '碱性', '特殊'] as const
  const colors = categories.map((category) => residueCategoryColor(category))
  assert.equal(new Set(colors).size, categories.length)
})

test('口袋残基面板按「关键在上、全部在下」组织，且支持多选', () => {
  const source = readSource('src/views/demo/Achievements.vue')

  // 多选状态是数组，不是单值
  assert.match(source, /const selectedResIds = ref<number\[\]>\(\[\]\)/)
  assert.doesNotMatch(source, /const selectedResId = ref<number \| null>/)
  assert.match(source, /selectedResIds\.includes\(/)
  assert.match(source, /function toggleResidue\(/)
  assert.match(source, /function selectAllKeyResidues\(/)
  assert.match(source, /function clearResidueSelection\(/)
  assert.match(source, /:selected-res-ids="selectedResIds"/)

  // 关键残基只取核心与关键两级
  assert.match(source, /const keyResidues = computed\(/)
  assert.match(source, /residue\.score_tier === 'core' \|\| residue\.score_tier === 'key'/)

  // 关键残基区必须在「全部残基」表之前
  const keyIndex = source.indexOf('class="key-residue-list"')
  const allIndex = source.indexOf('data-testid="all-residues-table"')
  assert.ok(keyIndex > 0, '缺少关键残基列表')
  assert.ok(allIndex > keyIndex, '全部残基表必须排在关键残基之后')

  // 全部残基表不列分数列
  const columnsBlock = source.slice(
    source.indexOf('const allResidueColumns = ['),
    source.indexOf('function allResidueRowClass')
  )
  assert.ok(columnsBlock.length > 0, '缺少全部残基列定义')
  assert.doesNotMatch(columnsBlock, /title: '评分'|title: '分数'/)
})

test('Mol* 相机对焦点必须是 Sphere3D，传普通对象会把相机写成 NaN', () => {
  const source = readSource('src/components/tasks/PocketViewer.vue')
  assert.match(source, /Sphere3D\.create\(/)
  assert.match(source, /focusSphere\(\s*Sphere3D\.create\(/)
  // 不能出现「直接把 { center, radius } 喂给 focusSphere」的写法
  assert.doesNotMatch(source, /focusSphere\(\s*\{/)
  // 选中残基变化时保留视角，不重新对焦
  assert.match(source, /keepCamera/)
  assert.match(source, /camera\.setState\(/)
})

test('只有选中的残基画球棍，关键残基不自动展开', () => {
  const viewer = readSource('src/components/tasks/PocketViewer.vue')
  // 选中残基用球棍表示
  assert.match(viewer, /'focus-residue'/)
  assert.match(viewer, /type: 'ball-and-stick'/)
  // 没有「关键残基」这个自动分组：不选就不画，选了才画
  assert.doesNotMatch(viewer, /'key-residues'/)
  assert.doesNotMatch(viewer, /keyResIds/)
  // 卡通层要把选中的残基排除，否则同一个原子被画两遍，球棍埋在丝带里
  assert.match(viewer, /const peripheral = props\.resIds\.filter\(\(id\) => !selected\.has\(id\)\)/)
  // 图例说明球棍形态
  assert.match(viewer, /选中残基（球棍）/)

  const page = readSource('src/views/demo/Achievements.vue')
  assert.doesNotMatch(page, /:key-res-ids/)
})

test('界面上不写打分工与疏水指数的解释性文字', () => {
  const page = readSource('src/views/demo/Achievements.vue')
  assert.doesNotMatch(page, /贴近口袋中心 0\.45/)
  assert.doesNotMatch(page, /Kyte–Doolittle/)
  assert.doesNotMatch(page, /不是结合自由能/)

  const table = readSource('src/views/targets/PocketResidues.vue')
  assert.doesNotMatch(table, /贴近口袋中心 0\.45/)
})
