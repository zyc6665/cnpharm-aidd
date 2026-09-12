import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolRunInputForm from './ToolRunInputForm.vue'
import type { ToolSchema } from '@/types/models'

const schema: ToolSchema = {
  type: 'object',
  properties: {
    protein_pdb: { type: 'file', title: 'Protein PDB', format: 'file' },
    model_choice: { type: 'string', title: 'Model weight', default: 'auto' },
  },
  required: ['protein_pdb'],
}

describe('ToolRunInputForm', () => {
  const stubs = {
    StandardArtifactInputs: {
      props: ['slots'],
      template: '<div class="standard-artifact-inputs">standard {{ slots.length }}</div>',
    },
    ToolParameterForm: {
      props: ['schema'],
      template: '<div class="tool-parameter-form">{{ Object.keys(schema.properties).join(",") }}<slot name="file-field-extra" field-key="protein_pdb" :property="schema.properties.protein_pdb" /></div>',
    },
  }

  it('renders the standard artifact block only when the resolved surface requires it', () => {
    const wrapper = mount(ToolRunInputForm, {
      props: {
        schema,
        formState: {},
        fileList: {},
        selectedArtifacts: {},
        standardInputSlots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
        showStandardArtifactInputs: true,
        currentProjectId: 'project-1',
        projectArtifacts: [],
        selectedStandardArtifacts: {},
        standardInputFileList: {},
      },
      global: { stubs },
    })

    expect(wrapper.find('.standard-artifact-inputs').exists()).toBe(true)
    expect(wrapper.find('.tool-parameter-form').text()).toContain('protein_pdb,model_choice')
  })

  it('supports concrete standard input fields without rendering the standard block', () => {
    const wrapper = mount(ToolRunInputForm, {
      props: {
        schema,
        formState: {},
        fileList: {},
        selectedArtifacts: {},
        standardInputSlots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
        showStandardArtifactInputs: false,
        currentProjectId: undefined,
        projectArtifacts: [],
        selectedStandardArtifacts: {},
        standardInputFileList: {},
      },
      slots: {
        'file-field-extra': '<span class="field-extra">extra</span>',
      },
      global: { stubs },
    })

    expect(wrapper.find('.standard-artifact-inputs').exists()).toBe(false)
    expect(wrapper.find('.tool-parameter-form').exists()).toBe(true)
    expect(wrapper.find('.field-extra').exists()).toBe(true)
  })
})
