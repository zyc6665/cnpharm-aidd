import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  buildProjectDecisionsPath,
  buildProjectDesignPath,
  buildProjectTaskPath,
  buildProjectWorkflowPath,
  buildProjectWorkspaceNavItems,
  isProjectWorkspaceNavItemActive
} from './navigation'

test('项目工作台导航项覆盖所有项目内入口', () => {
  const items = buildProjectWorkspaceNavItems('project-1')

  assert.deepEqual(
    items.map(item => item.label),
    [
      '项目总览',
      '靶点与结构',
      '设计流程',
      '任务中心',
      '数据资产',
      '候选物',
      '结果中心',
      '决策记录',
      'Artifact 谱系',
      '项目设置'
    ]
  )
  assert.deepEqual(
    items.map(item => item.to),
    [
      '/projects/project-1',
      '/projects/project-1/targets',
      '/design?project_id=project-1',
      '/tasks?project_id=project-1',
      '/projects/project-1/assets',
      '/projects/project-1/candidates',
      '/projects/project-1/results',
      '/projects/project-1/decisions',
      '/projects/project-1/lineage',
      '/projects/project-1/settings'
    ]
  )
})

test('决策记录导航项排在结果中心之后、Artifact 谱系之前', () => {
  const items = buildProjectWorkspaceNavItems('project-1')
  const keys = items.map(item => item.key)

  assert.equal(keys.indexOf('decisions'), keys.indexOf('results') + 1)
  assert.equal(keys.indexOf('decisions') + 1, keys.indexOf('lineage'))

  const decisions = items.find(item => item.key === 'decisions')
  assert.ok(decisions, '缺少 decisions 导航项')
  assert.equal(decisions?.to, '/projects/project-1/decisions')
  assert.equal(buildProjectDecisionsPath('project-1'), '/projects/project-1/decisions')
})

test('项目任务路径编码 project_id，画布编排仍保留项目路由', () => {
  assert.equal(buildProjectTaskPath('project 1'), '/tasks?project_id=project%201')
  assert.equal(buildProjectDesignPath('project 1'), '/design?project_id=project%201')
  // 画布编排不再是顶级导航，但路由与构造函数保留：它是设计流程的高级形态。
  assert.equal(buildProjectWorkflowPath('project-1'), '/projects/project-1/workflow')
})

test('项目工作台导航 active 规则支持普通项目路径和任务中心 query', () => {
  const [overview, targets, design, tasks] = buildProjectWorkspaceNavItems('project-1')

  assert.equal(
    isProjectWorkspaceNavItemActive(overview!, {
      currentPath: '/projects/project-1',
      currentProjectId: 'project-1'
    }),
    true
  )
  // 项目总览的路径是所有子页的前缀：进子页时只能高亮子页，不能连总览一起亮。
  assert.equal(
    isProjectWorkspaceNavItemActive(overview!, {
      currentPath: '/projects/project-1/settings',
      currentProjectId: 'project-1'
    }),
    false
  )
  assert.equal(
    isProjectWorkspaceNavItemActive(targets!, {
      currentPath: '/projects/project-1/targets/target-1',
      currentProjectId: 'project-1'
    }),
    true
  )
  assert.equal(
    isProjectWorkspaceNavItemActive(design!, {
      currentPath: '/design',
      currentProjectId: 'project-1',
      queryProjectId: 'project-1'
    }),
    true
  )
  // 画布编排是设计流程的高级形态：进画布时这一项仍然亮着。
  assert.equal(
    isProjectWorkspaceNavItemActive(design!, {
      currentPath: '/projects/project-1/workflow',
      currentProjectId: 'project-1'
    }),
    true
  )
  // 别的项目在设计流程页时，本项目的这一项不能亮。
  assert.equal(
    isProjectWorkspaceNavItemActive(design!, {
      currentPath: '/design',
      currentProjectId: 'project-1',
      queryProjectId: 'project-2'
    }),
    false
  )
  assert.equal(
    isProjectWorkspaceNavItemActive(tasks!, {
      currentPath: '/tasks',
      currentProjectId: 'project-1',
      queryProjectId: 'project-1'
    }),
    true
  )
  assert.equal(
    isProjectWorkspaceNavItemActive(tasks!, {
      currentPath: '/tasks',
      currentProjectId: 'project-1',
      queryProjectId: 'project-2'
    }),
    false
  )
})
