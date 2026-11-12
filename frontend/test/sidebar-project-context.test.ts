import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  resolveActiveProjectId,
  resolveProjectSwitchTarget
} from '../src/domain/projects/project-switch'

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), 'utf8')
}

describe('换项目时的落点', () => {
  it('项目子页面：同名路由换参数，其余查询参数保留', () => {
    const target = resolveProjectSwitchTarget(
      {
        name: 'ProjectTargets',
        path: '/projects/old/targets',
        params: { projectId: 'old' },
        query: { foo: '1' }
      },
      'new'
    )
    expect(target).toEqual({
      name: 'ProjectTargets',
      params: { projectId: 'new' },
      query: { foo: '1' }
    })
  })

  it('用查询参数携带项目的页面：只换查询参数', () => {
    const target = resolveProjectSwitchTarget(
      {
        name: 'Tasks',
        path: '/tasks',
        params: {},
        query: { project_id: 'old', status: 'running' }
      },
      'new'
    )
    expect(target).toEqual({
      path: '/tasks',
      query: { project_id: 'new', status: 'running' }
    })
  })

  it('与项目无关的页面：回到该项目总览', () => {
    const target = resolveProjectSwitchTarget({ name: 'Tools', path: '/tools', params: {}, query: {} }, 'new')
    expect(target).toEqual({ path: '/projects/new' })
  })

  it('当前项目 id：路径参数优先于查询参数', () => {
    expect(resolveActiveProjectId({ projectId: 'from-path' }, { project_id: 'from-query' })).toBe('from-path')
    expect(resolveActiveProjectId({}, { project_id: 'from-query' })).toBe('from-query')
    expect(resolveActiveProjectId({}, {})).toBe('')
  })
})

describe('侧边栏项目上下文', () => {
  it('挂进 AppShell，并且有切换器、全部项目与折叠态入口', () => {
    const shell = source('src/components/layout/AppShell.vue')
    expect(shell).toContain('<SidebarProjectContext :collapsed="collapsed" />')
    expect(shell).toContain(
      "import SidebarProjectContext from '@/components/layout/SidebarProjectContext.vue'"
    )

    const component = source('src/components/layout/SidebarProjectContext.vue')
    expect(component).toContain('data-testid="sidebar-project-switch"')
    expect(component).toContain('data-testid="sidebar-project-all"')
    expect(component).toContain('data-testid="sidebar-project-overview"')
    expect(component).toContain('data-testid="sidebar-project-collapsed"')
    // 侧边栏不再重复项目内横向导航（项目页面自己会渲染一份）
    expect(component).not.toContain('buildProjectWorkspaceNavItems(')
  })

  it('切换动作走 domain 的落点解析，不自己拼路径', () => {
    const composable = source('src/composables/useActiveProject.ts')
    expect(composable).toContain('resolveProjectSwitchTarget(')
    expect(composable).toContain('router.push(')
  })
})
