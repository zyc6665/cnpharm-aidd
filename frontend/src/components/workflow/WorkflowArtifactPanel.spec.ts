import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import WorkflowArtifactPanel from './WorkflowArtifactPanel.vue'
import { useUserStore } from '@/stores'
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
    useUserStore().token = 'token'
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
})
