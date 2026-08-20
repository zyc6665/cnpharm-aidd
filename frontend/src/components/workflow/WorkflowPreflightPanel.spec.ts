import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import type { WorkflowPreflightSummary } from '@/workflow/preflight'
import WorkflowPreflightPanel from './WorkflowPreflightPanel.vue'

describe('WorkflowPreflightPanel', () => {
  const basePreflight: WorkflowPreflightSummary = {
    canRun: true,
    runnableCount: 1,
    blockedCount: 0,
    completedCount: 0,
    runningCount: 0,
    failedCount: 0,
    issues: [],
    primaryMessage: '有 1 个节点可运行',
    resourceSummaries: [],
  }

  const mountPanel = (preflight = basePreflight) => mount(WorkflowPreflightPanel, {
    props: {
      preflight,
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

  it('使用指标卡和分组区块组织预检内容', () => {
    const wrapper = mountPanel({
      ...basePreflight,
      blockedCount: 2,
      completedCount: 3,
      failedCount: 1,
      issues: [
        {
          id: 'missing-input',
          nodeId: 'dock-ligands',
          nodeTitle: 'Dock Ligands',
          type: 'missing_workflow_input',
          severity: 'warning',
          title: '缺少输入',
          detail: '需要 ligand_structure@1',
        },
      ],
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
    })

    expect(wrapper.find('.preflight-metrics').exists()).toBe(true)
    expect(wrapper.findAll('.preflight-metric')).toHaveLength(4)
    expect(wrapper.findAll('.preflight-section')).toHaveLength(3)
    expect(wrapper.text()).toContain('检查项')
  })

  it('展示可运行工具节点的资源需求摘要', () => {
    const wrapper = mountPanel({
      ...basePreflight,
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
    })

    expect(wrapper.text()).toContain('资源需求')
    expect(wrapper.text()).toContain('AutoDock Vina')
    expect(wrapper.text()).toContain('docker_image')
    expect(wrapper.text()).toContain('medium · CPU 8 · MEM 16GB · ETA 30m')
  })
})
