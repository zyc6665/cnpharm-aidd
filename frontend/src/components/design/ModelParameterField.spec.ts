import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { SchemaProperty } from '@/types/models'
import ModelParameterField from './ModelParameterField.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: () => false }),
}))

const NumberInputStub = {
  name: 'AInputNumber',
  props: ['value', 'min', 'max', 'step', 'precision', 'disabled'],
  template: '<input class="number-input" type="number" />',
}

const TextInputStub = {
  name: 'AInput',
  props: ['value', 'maxlength', 'placeholder', 'disabled'],
  template: '<input class="text-input" type="text" />',
}

const stubs = {
  AFormItem: { props: ['label', 'required', 'extra'], template: '<div><slot /></div>' },
  AInputNumber: NumberInputStub,
  AInput: TextInputStub,
  ATextarea: { template: '<textarea class="textarea-input" />' },
  ASelect: { template: '<select class="select-input" />' },
  ASwitch: { template: '<button class="switch-input" />' },
}

function mountField(property: SchemaProperty, value?: unknown, fieldKey = 'num_samples') {
  return mount(ModelParameterField, {
    props: { fieldKey, property, value: value as never },
    global: { stubs },
  })
}

describe('ModelParameterField', () => {
  it('renders integer parameters as numeric inputs with step 1 and precision 0', () => {
    const wrapper = mountField({ type: 'integer', minimum: 1, maximum: 1000 }, 100)

    expect(wrapper.find('.text-input').exists()).toBe(false)
    const input = wrapper.findComponent(NumberInputStub)
    expect(input.exists()).toBe(true)
    expect(input.props('step')).toBe(1)
    expect(input.props('precision')).toBe(0)
    expect(input.props('min')).toBe(1)
    expect(input.props('max')).toBe(1000)
  })

  it('keeps decimal parameters on the numeric input with fractional precision', () => {
    const wrapper = mountField({ type: 'number' }, 1.5, 'pocket_radius')

    const input = wrapper.findComponent(NumberInputStub)
    expect(input.exists()).toBe(true)
    expect(input.props('precision')).toBe(3)
  })

  it('renders string parameters as text inputs', () => {
    const wrapper = mountField({ type: 'string' }, 'value', 'label')

    expect(wrapper.findComponent(NumberInputStub).exists()).toBe(false)
    expect(wrapper.find('.text-input').exists()).toBe(true)
  })
})
