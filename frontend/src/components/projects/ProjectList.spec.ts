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
    membership: { id: 'membership-1', role: 'owner' },
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-31T08:30:00Z'
  }
]

describe('ProjectList', () => {
  it('从工作台进入项目总览页，而不是直接进入研究会话页', () => {
    const wrapper = mount(ProjectList, {
      props: { projects },
      global: {
        plugins: [i18n],
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a :href="to"><slot /></a>'
          },
          AButton: { template: '<button><slot /></button>' },
          APopconfirm: { template: '<span><slot /></span>' },
          FolderOpenOutlined: true
        }
      }
    })

    expect(wrapper.get('.project-row').attributes('href')).toBe('/projects/project-1')
    expect(wrapper.text()).toContain('项目总览')
  })
})
