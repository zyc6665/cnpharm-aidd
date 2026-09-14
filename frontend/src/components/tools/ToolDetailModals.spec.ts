import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolDetailModals from './ToolDetailModals.vue'
import type { ToolExampleFilePreview } from '@/types/models'
import i18n from '@/locales'

const preview: ToolExampleFilePreview = {
  field: 'protein_pdb',
  filename: 'protein.pdb',
  content: 'ATOM 1 N MET',
  truncated: true,
  previewable: true,
}

describe('ToolDetailModals', () => {
  const stubs = {
    AModal: {
      props: ['open', 'title'],
      emits: ['update:open'],
      template: `
        <section v-if="open" class="modal-stub">
          <h2>{{ title }}</h2>
          <button type="button" data-testid="close-modal" @click="$emit('update:open', false)">close</button>
          <slot />
        </section>
      `,
    },
    AAlert: {
      props: ['message'],
      template: '<div class="alert-stub">{{ message }}</div>',
    },
    AEmpty: {
      props: ['description'],
      template: '<div class="empty-stub">{{ description }}</div>',
    },
    SkeletonCard: { template: '<div class="skeleton-stub" />' },
  }

  it('renders example preview content and propagates preview close events', async () => {
    const wrapper = mount(ToolDetailModals, {
      props: {
        previewOpen: true,
        documentationOpen: false,
        previewLoading: false,
        preview,
        documentationHtml: '<p>Tool docs</p>',
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.text()).toContain('protein.pdb')
    expect(wrapper.text()).toContain('ATOM 1 N MET')
    expect(wrapper.find('.alert-stub').exists()).toBe(true)

    await wrapper.find('[data-testid="close-modal"]').trigger('click')

    expect(wrapper.emitted('update:previewOpen')).toEqual([[false]])
  })

  it('renders loading and unavailable preview states', async () => {
    const wrapper = mount(ToolDetailModals, {
      props: {
        previewOpen: true,
        documentationOpen: false,
        previewLoading: true,
        preview: null,
        documentationHtml: '',
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.find('.skeleton-stub').exists()).toBe(true)

    await wrapper.setProps({
      previewLoading: false,
      preview: { ...preview, content: undefined, previewable: false, truncated: false },
    })

    expect(wrapper.find('.skeleton-stub').exists()).toBe(false)
    expect(wrapper.find('.empty-stub').exists()).toBe(true)
  })

  it('renders documentation html and propagates documentation close events', async () => {
    const wrapper = mount(ToolDetailModals, {
      props: {
        previewOpen: false,
        documentationOpen: true,
        previewLoading: false,
        preview: null,
        documentationHtml: '<h1>LVpocket</h1><p>Predict pockets</p>',
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.find('.tool-documentation-content').html()).toContain('<h1>LVpocket</h1>')
    expect(wrapper.text()).toContain('Predict pockets')

    await wrapper.find('[data-testid="close-modal"]').trigger('click')

    expect(wrapper.emitted('update:documentationOpen')).toEqual([[false]])
  })
})
