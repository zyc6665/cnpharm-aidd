import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
/* eslint-disable vue/one-component-per-file, vue/require-prop-types -- 测试用 stub 组件 */
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import NodeInputBindingPanel from './NodeInputBindingPanel.vue'
import type { WorkflowCanvasNode, WorkflowCanvasPreset } from '@/workflow/canvas-types'
import type { WorkflowInputRequirement } from '@/workflow/workflow-definitions'

const ROOT = resolve(__dirname, '../../../..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(ROOT, relativePath), 'utf8')
}

const inputNode: WorkflowCanvasNode = {
  id: 'input-protein',
  type: 'input',
  titleKey: 'workflow.nodeLibrary.inputProtein.title',
  position: { x: 0, y: 0 },
  requiredInputTypes: ['protein_pdb']
}

const requirements: WorkflowInputRequirement[] = [
  { key: 'protein_pdb', semanticType: 'protein_pdb', label: 'protein_pdb' }
]

const optionsBySemanticType = {
  protein_pdb: [
    { value: 'artifact_version:version-1', label: 'EGFR prepared · v3' }
  ]
}

const ASelectStub = defineComponent({
  name: 'ASelectStub',
  props: ['value', 'options', 'placeholder'],
  emits: ['change'],
  template:
    '<select data-testid="node-input-binding-select"><option v-for="option in options" :key="option.value">{{ option.label }}</option></select>'
})

const AUploadStub = defineComponent({
  name: 'AUploadStub',
  props: ['beforeUpload', 'showUploadList'],
  template: '<span><slot /></span>'
})

const stubs = {
  'a-select': ASelectStub,
  'a-upload': AUploadStub,
  'a-button': {
    props: ['disabled'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
  },
  'a-alert': { props: ['message'], template: '<div data-testid="alert-stub">{{ message }}</div>' }
}

function mountPanel(overrides: Record<string, unknown> = {}) {
  return mount(NodeInputBindingPanel, {
    props: {
      node: inputNode,
      requirements,
      selections: {},
      optionsBySemanticType,
      canUpload: true,
      ...overrides
    },
    global: { plugins: [i18n], stubs }
  })
}

describe('NodeInputBindingPanel', () => {
  it('resolves the requirement from the node declaration and lists project artifacts', () => {
    const wrapper = mountPanel()

    expect(wrapper.find('[data-testid="node-input-binding-select"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('EGFR prepared · v3')
    expect(wrapper.find('[data-testid="node-input-binding-empty"]').exists()).toBe(false)
  })

  it('falls back to the outgoing edge artifact type when the node declares nothing', () => {
    const template: WorkflowCanvasPreset = {
      id: 'preset',
      kind: 'pocket',
      nameKey: 'preset.name',
      nodes: [],
      edges: [{ id: 'edge-1', source: 'input-protein', target: 'tool-prep', artifactType: 'protein_pdb' }]
    }
    const wrapper = mountPanel({
      node: { ...inputNode, requiredInputTypes: undefined },
      template
    })

    expect(wrapper.text()).toContain('EGFR prepared · v3')
  })

  it('emits select with the requirement key', async () => {
    const wrapper = mountPanel()

    wrapper.findComponent(ASelectStub).vm.$emit('change', 'artifact_version:version-1')

    expect(wrapper.emitted('select')).toEqual([['protein_pdb', 'artifact_version:version-1']])
  })

  it('emits upload with the requirement key and never performs a real upload', () => {
    const wrapper = mountPanel()

    const upload = wrapper.findComponent(AUploadStub)
    const beforeUpload = upload.props('beforeUpload') as (file: File) => boolean
    const result = beforeUpload(new File(['pdb'], 'receptor.pdb'))

    expect(wrapper.emitted('upload')?.[0]?.[0]).toBe('protein_pdb')
    expect(wrapper.emitted('upload')?.[0]?.[1]).toBeInstanceOf(File)
    expect(result).toBe(false)
  })

  it('explains the empty option list instead of showing a silently empty dropdown', () => {
    const wrapper = mountPanel({ optionsBySemanticType: { protein_pdb: [] } })

    expect(wrapper.find('[data-testid="node-input-binding-empty"]').exists()).toBe(true)
  })

  it('explains the unresolved requirement instead of rendering a dead control', () => {
    const wrapper = mountPanel({
      node: { ...inputNode, requiredInputTypes: undefined },
      requirements: []
    })

    expect(wrapper.find('[data-testid="alert-stub"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="node-input-binding-select"]').exists()).toBe(false)
  })
})

describe('workflow canvas wiring', () => {
  it('renders the binding panel for input nodes instead of the no-tool alert', () => {
    const source = readSource('frontend/src/components/workflow/WorkflowNodeInspector.vue')

    expect(source).toContain('<NodeInputBindingPanel')
    expect(source).toContain('v-if="node.type === \'input\'"')
    expect(source).toContain('v-else')
    expect(source).toContain(':requirements="inputRequirements ?? []"')
  })

  it('shares one selection map between the inspector and the run configuration tab', () => {
    const source = readSource('frontend/src/views/workflow/index.vue')

    expect(source).toContain(':input-selections="workflowRunInputSelections"')
    expect(source).toContain(':input-requirements="workflowInputRequirementDetails"')
    expect(source).toContain('@select-input="handleWorkflowInputSelect"')
    expect(source).toContain('@upload-input="handleWorkflowInputUpload"')
  })

  it('passes a translated placeholder into the tool node artifact picker', () => {
    const runPanel = readSource('frontend/src/components/workflow/WorkflowNodeRunPanel.vue')
    const standardInputs = readSource('frontend/src/components/tools/StandardArtifactInputs.vue')

    expect(runPanel).toContain(':project-artifact-placeholder="t(\'tools.selectProjectArtifact\')"')
    expect(standardInputs).toContain('data-testid="standard-artifact-empty"')
    expect(standardInputs).toContain("t('tools.noCompatibleArtifact')")
  })
})
