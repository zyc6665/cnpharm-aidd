import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolParameterForm from '@/components/workflow/ToolParameterForm.vue'
import type { ToolSchema } from '@/types/models'

function makeSchema(overrides: Partial<ToolSchema> = {}): ToolSchema {
  return {
    type: 'object',
    properties: {},
    required: [],
    ...overrides,
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const noopProps: Record<string, any> = {}

describe('ToolParameterForm', () => {
  const globalStubs = {
    AFormItem: { template: '<div class="stub-form-item"><slot /></div>' },
    AInput: { template: '<input class="stub-input" />' },
    ATextarea: { template: '<textarea class="stub-textarea" />' },
    AInputNumber: { template: '<input class="stub-number" type="number" />' },
    ASwitch: { template: '<button class="stub-switch" />' },
    ASelect: { template: '<select class="stub-select"><slot /></select>' },
    ASelectOption: { template: '<option class="stub-option"><slot /></option>' },
    ArtifactFilePicker: { template: '<div class="stub-artifact-picker" />' },
  }

  it('渲染 string 输入字段', () => {
    const schema = makeSchema({
      properties: { smiles: { type: 'string', title: 'SMILES' } },
    })
    const wrapper = mount(ToolParameterForm, {
      props: { schema, formState: noopProps, fileList: noopProps, selectedArtifacts: noopProps },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.stub-form-item').exists()).toBe(true)
    expect(wrapper.find('.stub-input').exists()).toBe(true)
  })

  it('渲染 number 输入字段', () => {
    const schema = makeSchema({
      properties: { iterations: { type: 'number', title: 'Iterations' } },
    })
    const wrapper = mount(ToolParameterForm, {
      props: { schema, formState: noopProps, fileList: noopProps, selectedArtifacts: noopProps },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.stub-form-item').exists()).toBe(true)
    expect(wrapper.find('.stub-number').exists()).toBe(true)
  })

  it('渲染 boolean 开关字段', () => {
    const schema = makeSchema({
      properties: { verbose: { type: 'boolean', title: 'Verbose' } },
    })
    const wrapper = mount(ToolParameterForm, {
      props: { schema, formState: noopProps, fileList: noopProps, selectedArtifacts: noopProps },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.stub-form-item').exists()).toBe(true)
    expect(wrapper.find('.stub-switch').exists()).toBe(true)
  })

  it('渲染 select 枚举字段', () => {
    const schema = makeSchema({
      properties: { mode: { type: 'string', title: 'Mode', enum: ['fast', 'accurate'] } },
    })
    const wrapper = mount(ToolParameterForm, {
      props: { schema, formState: noopProps, fileList: noopProps, selectedArtifacts: noopProps },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.stub-form-item').exists()).toBe(true)
    expect(wrapper.find('.stub-select').exists()).toBe(true)
  })

  it('空 schema 不渲染内容', () => {
    const schema = makeSchema()
    const wrapper = mount(ToolParameterForm, {
      props: { schema, formState: noopProps, fileList: noopProps, selectedArtifacts: noopProps },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.stub-form-item').exists()).toBe(false)
  })
})
