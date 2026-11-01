import { h } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AppInlineError from './AppInlineError.vue'

describe('AppInlineError', () => {
  it('renders title, description and detail as an alert', () => {
    const wrapper = mount(AppInlineError, {
      props: {
        title: '结果列表加载失败',
        description: '可能是网络不稳定或服务暂时不可用',
        detail: 'HTTP 500'
      }
    })

    expect(wrapper.attributes('role')).toBe('alert')
    expect(wrapper.get('.app-inline-error__title').text()).toBe('结果列表加载失败')
    expect(wrapper.get('.app-inline-error__description').text()).toBe(
      '可能是网络不稳定或服务暂时不可用'
    )
    expect(wrapper.get('.app-inline-error__detail').text()).toBe('HTTP 500')
  })

  it('omits empty fields but keeps the alert region', () => {
    const wrapper = mount(AppInlineError, { props: { title: '加载失败' } })

    expect(wrapper.get('.app-inline-error__title').text()).toBe('加载失败')
    expect(wrapper.find('.app-inline-error__description').exists()).toBe(false)
    expect(wrapper.find('.app-inline-error__detail').exists()).toBe(false)
  })

  it('fires the retry handler when the slotted action is clicked', async () => {
    const onRetry = vi.fn()
    const wrapper = mount(AppInlineError, {
      props: { title: '加载失败' },
      slots: {
        default: () => h('button', { class: 'retry', onClick: onRetry }, '重试')
      }
    })

    await wrapper.get('.retry').trigger('click')

    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
