import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  buildProjectCandidateViewTabs,
  buildProjectDataViewTabs,
  buildProjectDecisionsPath,
  buildProjectDesignPath,
  buildProjectFlowViewTabs,
  buildProjectTaskPath,
  buildProjectWorkflowPath,
  buildProjectWorkspaceNavItems,
  isProjectWorkspaceNavItemActive
} from './navigation'

test('项目工作台导航项收敛为 5 个主入口 + 1 个项目设置', () => {
  const items = buildProjectWorkspaceNavItems('project-1')

  assert.deepEqual(
    items.map(item => item.label),
    [
      '项目总览',
      '研发流程',
      '任务中心',
      '数据与产物',
      '候选与决策',
      '项目设置'
    ]
  )
  assert.deepEqual(
    items.map(item => item.to),
    [
      '/projects/project-1',
      '/design?project_id=project-1',
      '/projects/project-1/tasks',
      '/projects/project-1/assets',
      '/projects/project-1/candidates',
      '/projects/project-1/settings'
    ]
  )
})

test('二级视图切换覆盖数据与产物、候选与决策、研发流程的所有原有页面', () => {
  assert.deepEqual(
    buildProjectDataViewTabs('project-1').map(item => item.to),
    [
      '/projects/project-1/assets',
      '/projects/project-1/results',
      '/projects/project-1/lineage'
    ]
  )
  assert.deepEqual(
    buildProjectCandidateViewTabs('project-1').map(item => item.to),
    [
      '/projects/project-1/candidates',
      '/projects/project-1/decisions'
    ]
  )
  assert.deepEqual(
    buildProjectFlowViewTabs('project-1').map(item => item.to),
    [
      '/design?project_id=project-1',
      '/projects/project-1/targets',
      '/projects/project-1/workflow'
    ]
  )
  assert.equal(buildProjectDecisionsPath('project-1'), '/projects/project-1/decisions')
})

test('项目任务路径编码 project_id，画布编排仍保留项目路由', () => {
  assert.equal(buildProjectTaskPath('project 1'), '/projects/project%201/tasks')
  assert.equal(buildProjectDesignPath('project 1'), '/design?project_id=project%201')
  // 画布编排不再是顶级导航，但路由与构造函数保留：它是设计流程的高级形态。
  assert.equal(buildProjectWorkflowPath('project-1'), '/projects/project-1/workflow')
})

test('项目工作台导航 active 规则支持聚合后的子视图与任务中心 query', () => {
  const [overview, design, tasks, assets, candidates] = buildProjectWorkspaceNavItems('project-1')

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
  // 靶点与结构、设计流程、画布编排都归属「研发流程」。
  assert.equal(
    isProjectWorkspaceNavItemActive(design!, {
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
      currentPath: '/projects/project-1/tasks',
      currentProjectId: 'project-1'
    }),
    true
  )
  assert.equal(
    isProjectWorkspaceNavItemActive(tasks!, {
      currentPath: '/projects/project-1/tasks/task-1',
      currentProjectId: 'project-1'
    }),
    true
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
  // 数据资产、结果中心、Artifact 谱系都点亮「数据与产物」。
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
  // 候选物与决策记录都点亮「候选与决策」。
  for (const path of [
    '/projects/project-1/candidates',
    '/projects/project-1/decisions'
  ]) {
    assert.equal(
      isProjectWorkspaceNavItemActive(candidates!, {
        currentPath: path,
        currentProjectId: 'project-1'
      }),
      true
    )
  }
})
