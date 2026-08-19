import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import WorkflowPreflightPanel from './WorkflowPreflightPanel.vue'

describe('WorkflowPreflightPanel', () => {
  it('展示可运行工具节点的资源需求摘要', () => {
    const wrapper = mount(WorkflowPreflightPanel, {
      props: {
        preflight: {
          canRun: true,
          runnableCount: 1,
          blockedCount: 0,
          completedCount: 0,
          runningCount: 0,
          failedCount: 0,
          issues: [],
          primaryMessage: '有 1 个节点可运行',
          resourceSummaries: [
            {
              id: 'dock-ligands-vina-docking-resources',
              nodeId: 'dock-ligands',
              nodeTitle: 'Dock Ligands',
              toolSlug: 'vina-docking',
              toolName: 'AutoDock Vina',
              executorType: 'docker_image',
              label: 'medium · CPU 8 · MEM 16GB · ETA 30m',
            },
          ],
        },
      },
      global: {
        plugins: [i18n],
        stubs: {
          ASpace: { template: '<div><slot /></div>' },
          ATag: { template: '<span><slot /></span>' },
          AButton: { template: '<button><slot /></button>' },
        },
      },
    })

    expect(wrapper.text()).toContain('资源需求')
    expect(wrapper.text()).toContain('AutoDock Vina')
    expect(wrapper.text()).toContain('docker_image')
    expect(wrapper.text()).toContain('medium · CPU 8 · MEM 16GB · ETA 30m')
  })
})
