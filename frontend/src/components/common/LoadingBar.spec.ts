import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import LoadingBar from './LoadingBar.vue'

describe('LoadingBar', () => {
  it('只在后台刷新时渲染，服务端与首屏都不占位', () => {
    const idle = mount(LoadingBar, { props: { active: false } })
    expect(idle.find('[data-testid="inline-loading-bar"]').exists()).toBe(false)

    const active = mount(LoadingBar, { props: { active: true } })
    const bar = active.find('[data-testid="inline-loading-bar"]')
    expect(bar.exists()).toBe(true)
    // 进度条是「在取数据」的提示，不是内容容器：必须是可视但无高度感的一条线，
    // 出现/消失都不会推动下方内容位移。
    expect(bar.attributes('role')).toBe('progressbar')
    expect(bar.findAll('span').length).toBe(1)
  })
})
