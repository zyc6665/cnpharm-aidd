import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('typed Artifact API 应暴露项目谱系图读取方法', () => {
  const source = readSource('src/api/artifacts.ts')

  assert.equal(source.includes('getProjectArtifactLineage'), true)
  assert.equal(source.includes("`/projects/${projectId}/artifact-lineage`"), true)
})

test('typed Artifact 类型应声明谱系图节点与边', () => {
  const source = readSource('src/types/artifacts.ts')

  assert.equal(source.includes('ArtifactLineageGraph'), true)
  assert.equal(source.includes('ArtifactLineageGraphNode'), true)
  assert.equal(source.includes('ArtifactLineageGraphEdge'), true)
  assert.equal(source.includes("'workflow_node'"), true)
  assert.equal(source.includes("'produced_by'"), true)
  assert.equal(source.includes("'derived_from'"), true)
})

test('项目总览应提供 Artifact 谱系入口', () => {
  const source = readSource('src/views/projects/Overview.vue')

  assert.equal(source.includes("`/projects/${projectId}/lineage`"), true)
  assert.equal(source.includes('Artifact 谱系'), true)
})

test('项目 Artifact 谱系页和路由应存在', () => {
  const routerSource = readSource('src/router/index.ts')
  const pagePath = resolve(rootDir, 'src/views/projects/ArtifactLineage.vue')

  assert.equal(existsSync(pagePath), true)
  assert.equal(routerSource.includes("path: '/projects/:projectId/lineage'"), true)
  assert.equal(routerSource.includes("name: 'ProjectArtifactLineage'"), true)
  assert.equal(routerSource.includes("import('@/views/projects/ArtifactLineage.vue')"), true)
  assert.equal(routerSource.includes("titleLiteral: 'Artifact 谱系'"), true)
})

test('Artifact 谱系页应加载项目图并交给图组件渲染', () => {
  const source = readSource('src/views/projects/ArtifactLineage.vue')

  assert.equal(source.includes('getProjectArtifactLineage'), true)
  assert.equal(source.includes('ArtifactLineageGraph'), true)
  assert.equal(source.includes(':graph="graph"'), true)
  assert.equal(source.includes('lineageLoadError'), true)
})

test('ArtifactLineageGraph 组件应展示节点、版本、来源任务和 workflow 节点关系', () => {
  const componentPath = resolve(rootDir, 'src/components/artifacts/ArtifactLineageGraph.vue')
  assert.equal(existsSync(componentPath), true)

  const source = readSource('src/components/artifacts/ArtifactLineageGraph.vue')
  assert.equal(source.includes('artifact-lineage-graph'), true)
  assert.equal(source.includes('artifact-lineage-node'), true)
  assert.equal(source.includes('artifact-lineage-edge'), true)
  assert.equal(source.includes('workflow_node'), true)
  assert.equal(source.includes('produced_by'), true)
  assert.equal(source.includes('derived_from'), true)
  assert.equal(source.includes('version_id'), true)
})
