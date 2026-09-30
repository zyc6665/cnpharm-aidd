import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolRunFormActions from './ToolRunFormActions.vue'
import i18n from '@/locales'

describe('ToolRunFormActions', () => {
  const stubs = {
    AFormItem: { template: '<div class="form-item-stub"><slot /></div>' },
    ASpace: { template: '<div class="space-stub"><slot /></div>' },
    AButton: {
      props: ['type', 'htmlType', 'size', 'loading', 'disabled'],
      emits: ['click'],
      template: `
        <button
          type="button"
          :data-type="type"
          :data-html-type="htmlType"
          :data-size="size"
          :data-loading="loading"
          :disabled="disabled"
          @click="$emit('click')"
        >
          <slot />
        </button>
      `,
    },
    PlayCircleOutlined: { template: '<i class="play-icon" />' },
    LoginOutlined: { template: '<i class="login-icon" />' },
  }

  it('renders submit and reset actions with submit state', async () => {
    const wrapper = mount(ToolRunFormActions, {
      props: { submitting: true, canSubmit: false },
      global: { plugins: [i18n], stubs },
    })

    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(2)
    expect(buttons[0]!.attributes('data-type')).toBe('primary')
    expect(buttons[0]!.attributes('data-html-type')).toBe('submit')
    expect(buttons[0]!.attributes('data-loading')).toBe('true')
    expect(buttons[0]!.attributes('disabled')).toBeDefined()
    expect(wrapper.find('.play-icon').exists()).toBe(true)

    await buttons[1]!.trigger('click')

    expect(wrapper.emitted('reset')).toEqual([[]])
  })

  it('offers a direct login action when the user is not authenticated', async () => {
    const wrapper = mount(ToolRunFormActions, {
      props: { submitting: false, canSubmit: false, loginRequired: true },
      global: { plugins: [i18n], stubs },
    })

    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(2)
    expect(wrapper.find('.login-icon').exists()).toBe(true)
    expect(buttons[0]!.attributes('disabled')).toBeUndefined()

    await buttons[0]!.trigger('click')

    expect(wrapper.emitted('login')).toEqual([[]])
  })
})
