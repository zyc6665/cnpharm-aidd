import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import ResizableWorkbenchSidebar from './ResizableWorkbenchSidebar.vue'

describe('ResizableWorkbenchSidebar', () => {
  it('keeps sidebar accessibility labels in locale keys', () => {
    const source = readFileSync(resolve('src/components/workflow/ResizableWorkbenchSidebar.vue'), 'utf8')
    const zhSource = readFileSync(resolve('src/locales/zh-CN/index.ts'), 'utf8')
    const enSource = readFileSync(resolve('src/locales/en-US/index.ts'), 'utf8')

    for (const marker of [
      'workflow.workbenchSidebar.expand',
      'workflow.workbenchSidebar.collapse',
      'workflow.workbenchSidebar.resize',
    ]) {
      expect(source).toContain(marker)
    }

    for (const marker of ['workbenchSidebar', 'expand', 'collapse', 'resize']) {
      expect(zhSource).toContain(marker)
      expect(enSource).toContain(marker)
    }

    for (const literal of ['展开侧边栏', '折叠侧边栏', '调整侧边栏宽度']) {
      expect(source).not.toContain(literal)
    }
  })

  it('renders slot content and emits width changes from the resize handle', async () => {
    const wrapper = mount(ResizableWorkbenchSidebar, {
      props: {
        side: 'left',
        width: 320,
        collapsed: false,
        minWidth: 280,
        maxWidth: 480,
      },
      slots: { default: '<div data-testid="sidebar-content">Tools</div>' },
      global: { plugins: [i18n] },
    })

    expect(wrapper.find('[data-testid="sidebar-content"]').text()).toBe('Tools')
    expect(wrapper.attributes('style')).toContain('width: 320px')

    wrapper.find('[data-testid="sidebar-resize-handle"]').element.dispatchEvent(
      new PointerEvent('pointerdown', { clientX: 320, button: 0 })
    )
    await wrapper.vm.$nextTick()
    window.dispatchEvent(new PointerEvent('pointermove', { clientX: 380 }))
    window.dispatchEvent(new PointerEvent('pointerup'))

    const widthEvents = wrapper.emitted('update:width') ?? []
    expect(widthEvents[widthEvents.length - 1]).toEqual([380])
  })

  it('uses collapsed width and emits collapsed toggle', async () => {
    const wrapper = mount(ResizableWorkbenchSidebar, {
      props: {
        side: 'right',
        width: 380,
        collapsed: true,
        minWidth: 320,
        maxWidth: 560,
      },
      global: { plugins: [i18n] },
    })

    expect(wrapper.attributes('style')).toContain('width: 56px')
    await wrapper.find('[data-testid="sidebar-collapse-toggle"]').trigger('click')
    expect(wrapper.emitted('update:collapsed')).toEqual([[false]])
  })
})
