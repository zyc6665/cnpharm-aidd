import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import ProjectList from './ProjectList.vue'
import type { ResearchProject } from '@/types/projects'

const projects: ResearchProject[] = [
  {
    id: 'project-1',
    organization_id: 'organization-1',
    created_by: 'user-1',
    name: 'EGFR 口袋研究',
    goal: '寻找可成药结合口袋',
    status: 'active',
    model_policy: {},
    data_policy: {},
    role: 'owner',
    membership: { id: 'membership-1', role: 'owner' },
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-31T08:30:00Z'
  }
]

describe('ProjectList', () => {
  const mountList = (list: ResearchProject[]) =>
    mount(ProjectList, {
      props: { projects: list },
      global: {
        plugins: [i18n],
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a :href="to"><slot /></a>'
          },
          AButton: { template: '<button v-bind="$attrs"><slot /></button>' },
          APopconfirm: { template: '<span><slot /></span>' },
          FolderOpenOutlined: true
        }
      }
    })

  it('从工作台进入项目总览页，而不是直接进入研究会话页', () => {
    const wrapper = mountList(projects)

    expect(wrapper.get('.project-row').attributes('href')).toBe('/projects/project-1')
    expect(wrapper.text()).toContain('项目总览')
  })

  it('归档项目显示「撤销归档」而不是「归档」', () => {
    const wrapper = mountList([{ ...projects[0]!, status: 'archived' }])

    const labels = wrapper.findAll('button').map(button => button.text())
    expect(labels).toContain('撤销归档')
    expect(labels).not.toContain('归档')
  })

  it('只读成员看不到归档与撤销归档的入口', () => {
    const wrapper = mountList([
      { ...projects[0]!, status: 'archived', role: 'viewer' },
      { ...projects[0]!, status: 'active', role: 'viewer' }
    ])

    const labels = wrapper.findAll('button').map(button => button.text())
    expect(labels).not.toContain('归档')
    expect(labels).not.toContain('撤销归档')
  })
})
