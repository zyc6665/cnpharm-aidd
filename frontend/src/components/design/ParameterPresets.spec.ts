import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { ToolSchema } from '@/types/models'
import ParameterPresets from './ParameterPresets.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('ant-design-vue', () => ({
  message: {
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

const stubs = {
  ASelect: {
    props: ['options', 'value', 'placeholder', 'disabled'],
    emits: ['change'],
    template: `<select @change="$emit('change', $event.target.value)">
      <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
    </select>`,
  },
  AButton: {
    emits: ['click'],
    template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
  },
  ATag: {
    emits: ['close'],
    template: '<span class="tag"><slot /><button class="tag-close" @click="$emit(\'close\')">x</button></span>',
  },
  AModal: {
    props: ['open', 'title'],
    emits: ['ok'],
    template: '<div v-if="open" class="modal"><slot /><button class="modal-ok" @click="$emit(\'ok\')">ok</button></div>',
  },
  AForm: { template: '<form><slot /></form>' },
  AFormItem: { template: '<div><slot /></div>' },
  AInput: {
    props: ['value', 'placeholder'],
    emits: ['update:value', 'press-enter'],
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
  },
}

const schema: ToolSchema = {
  type: 'object',
  properties: {
    num_samples: { type: 'integer', default: 100 },
    batch_size: { type: 'integer', default: 2 },
    seed: { type: 'integer' },
  },
}

function mountPresets(values: Record<string, number> = {}) {
  return mount(ParameterPresets, {
    props: { schema, values },
    global: { stubs },
  })
}

describe('ParameterPresets', () => {
  beforeEach(() => localStorage.clear())

  it('加载内置预设时只保留 schema 声明的参数', async () => {
    const wrapper = mountPresets()
    await wrapper.get('select').setValue('quick')

    const [payload] = wrapper.emitted('load')?.[0] as [Record<string, number>]
    expect(payload).toEqual({ num_samples: 20 })
  })

  it('保存当前参数到 localStorage 并渲染为可删除标签', async () => {
    const wrapper = mountPresets({ num_samples: 160, batch_size: 2, unknown: 1 })
    await wrapper.get('[data-testid="parameter-preset-save"]').trigger('click')
    await wrapper.get('input').setValue('我的预设')
    await wrapper.get('.modal-ok').trigger('click')

    const stored = JSON.parse(localStorage.getItem('design:parameter-presets:molecule') ?? '[]')
    expect(stored).toHaveLength(1)
    expect(stored[0].name).toBe('我的预设')
    expect(stored[0].params).toEqual({ num_samples: 160, batch_size: 2 })
    expect(wrapper.text()).toContain('我的预设')
  })

  it('从 localStorage 恢复自定义预设，并在 storageKey 切换时同步刷新', async () => {
    localStorage.setItem(
      'design:parameter-presets:molecule',
      JSON.stringify([{ id: 'p1', name: '恢复的预设', params: { num_samples: 50 } }])
    )
    localStorage.setItem(
      'design:parameter-presets:other',
      JSON.stringify([{ id: 'p2', name: '另一模型预设', params: { num_samples: 80 } }])
    )
    const wrapper = mountPresets()
    expect(wrapper.text()).toContain('恢复的预设')

    await wrapper.setProps({ storageKey: 'design:parameter-presets:other' })
    expect(wrapper.text()).toContain('另一模型预设')
    expect(wrapper.text()).not.toContain('恢复的预设')
  })
})
