import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import WorkflowArtifactPanel from './WorkflowArtifactPanel.vue'
import { useUserStore } from '@/stores'
import type { UserInfo } from '@/types/models'
import i18n from '@/locales'
import type { WorkflowTaskRef } from '@/workflow/artifact-types'

const stubs = {
  AAlert: { template: '<div><slot name="message" /></div>' },
  AButton: { template: '<button><slot /></button>' },
  AEmpty: { props: ['description'], template: '<div>{{ description }}</div>' },
  ATag: { template: '<span><slot /></span>' },
}

describe('WorkflowArtifactPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // 登录态由 Cookie 会话 + userInfo 决定，测试直接注入用户信息
    useUserStore().userInfo = { id: 'user-1', username: 'tester' } as UserInfo
  })

  it('renders the active node task passed by the workflow page', () => {
    const activeTask: WorkflowTaskRef = {
      id: 'task-current-node',
      name: 'Current Node Task',
      tool_id: 'tool-fetch-pdb',
      tool_slug: 'builtin-fetch-pdb',
      status: 'running',
      progress: 45,
      created_at: '2026-08-20T00:00:00Z',
    }

    const wrapper = mount(WorkflowArtifactPanel, {
      props: {
        selectedToolSlug: 'builtin-fetch-pdb',
        activeTask,
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.text()).toContain('Current Node Task')
    expect(wrapper.text()).toContain('running')
    expect(wrapper.text()).toContain('45%')
  })

  it('renders current and recent artifact trees through one shared template', () => {
    const source = readFileSync(resolve('src/components/workflow/WorkflowArtifactPanel.vue'), 'utf8')

    expect(source.match(/class="artifact-group"/g) ?? []).toHaveLength(1)
    expect(source).toContain('artifactSections')
    expect(source).not.toContain('currentGroupNodes.length > 0')
    expect(source).not.toContain('recentGroupNodes.length > 0')
  })
})
