import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import type { WorkflowPreflightSummary } from '@/workflow/preflight'
import WorkflowPreflightPanel from './WorkflowPreflightPanel.vue'

describe('WorkflowPreflightPanel', () => {
  it('keeps auto repair panel labels in locale keys', () => {
    const source = readFileSync(resolve('src/components/workflow/WorkflowPreflightPanel.vue'), 'utf8')
    const zhSource = readFileSync(resolve('src/locales/zh-CN/index.ts'), 'utf8')
    const enSource = readFileSync(resolve('src/locales/en-US/index.ts'), 'utf8')

    for (const marker of ['workflow.preflight.applyAutoRepair', 'workflow.preflight.autoRepairTitle']) {
      expect(source).toContain(marker)
    }

    for (const marker of ['applyAutoRepair', 'autoRepairTitle']) {
      expect(zhSource).toContain(marker)
      expect(enSource).toContain(marker)
    }

    for (const literal of ['一键补齐准备节点', '可自动补齐']) {
      expect(source).not.toContain(literal)
    }
  })

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
      repairableCount: 0,
    },
    global: {
      plugins: [i18n],
      stubs: {
        ASpace: { template: '<div><slot /></div>' },
        ATag: { template: '<span><slot /></span>' },
        AButton: {
          emits: ['click'],
          template: '<button v-bind="$attrs" @click="$emit(\'click\')"><slot /></button>',
        },
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

  it('存在可自动修复项时应展示一键补齐动作', async () => {
    const wrapper = mountPanel({
      ...basePreflight,
      canRun: false,
      runnableCount: 0,
      blockedCount: 1,
      primaryMessage: '存在标准产物需要准备或转换',
      issues: [
        {
          id: 'dock-needs-preparation-receptor',
          nodeId: 'dock',
          nodeTitle: 'Dock',
          type: 'needs_preparation',
          severity: 'warning',
          title: '需要先准备输入产物',
          detail: '缺少 receptor_pdbqt。建议运行 builtin-protein-preparation。',
        },
      ],
    })

    await wrapper.setProps({ repairableCount: 1 })
    expect(wrapper.text()).toContain('一键补齐准备节点')

    await wrapper.find('[data-testid="apply-workflow-auto-repair"]').trigger('click')

    expect(wrapper.emitted('apply-auto-repair')).toHaveLength(1)
  })

  it('展示自动补齐解释，说明缺失 role 和将使用的工具', async () => {
    const wrapper = mountPanel({
      ...basePreflight,
      canRun: false,
      runnableCount: 0,
      blockedCount: 1,
      primaryMessage: '存在标准产物需要准备或转换',
      issues: [],
    })

    await wrapper.setProps({
      repairableCount: 1,
      repairActions: [
        {
          id: 'repair-dock-receptor',
          sourceEdgeId: 'edge-fetch-dock',
          sourceNodeId: 'fetch-pdb',
          targetNodeId: 'dock',
          targetNodeTitle: 'Dock',
          inputSlotName: 'receptor',
          artifactType: 'protein_structure@1',
          toolSlug: 'remote-protein-prep-api',
          toolName: 'Remote Protein Preparation API',
          requiredRoles: ['receptor_pdbqt'],
          roleLabels: ['受体 PDBQT (receptor_pdbqt)'],
          reason: 'Dock 的 receptor 需要受体 PDBQT (receptor_pdbqt)，可通过 Remote Protein Preparation API 自动补齐。',
          position: { x: 200, y: 96 },
        },
      ],
    })

    expect(wrapper.find('[data-testid="workflow-auto-repair-explanations"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('可自动补齐')
    expect(wrapper.text()).toContain('Dock')
    expect(wrapper.text()).toContain('受体 PDBQT (receptor_pdbqt)')
    expect(wrapper.text()).toContain('Remote Protein Preparation API')
  })
})
