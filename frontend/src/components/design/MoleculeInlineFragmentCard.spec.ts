import { describe, it, expect, vi } from 'vitest'
import { mount as baseMount } from '@vue/test-utils'
import MoleculeInlineFragmentCard from './MoleculeInlineFragmentCard.vue'
import type { InlineFragmentAtom, InlineFragmentBond } from './MoleculeInlineFragmentCard.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, te: () => false })
}))

const mount = (component: typeof MoleculeInlineFragmentCard, options: Parameters<typeof baseMount>[1] = {}) =>
  baseMount(component, {
    ...options,
    global: {
      stubs: {
        'a-tag': { props: ['color'], template: '<span :color="color"><slot /></span>' },
        'a-button': { props: ['disabled', 'type', 'size'], template: '<button :disabled="disabled"><slot /></button>' },
        ...(options.global?.stubs ?? {})
      }
    }
  })

describe('MoleculeInlineFragmentCard', () => {
  const createMockAtoms = (): InlineFragmentAtom[] => [
    { index: 0, element: 'C', x2d: 0, y2d: 0 },
    { index: 1, element: 'N', x2d: 1.5, y2d: 0, isHetero: true },
    { index: 2, element: 'O', x2d: 3, y2d: 0, isHetero: true },
    { index: 3, element: 'C', x2d: 1.5, y2d: 1.5 }
  ]

  const createMockBonds = (): InlineFragmentBond[] => [
    { a: 0, b: 1, order: 1 },
    { a: 1, b: 2, order: 2 },
    { a: 1, b: 3, order: 1 }
  ]

  it('renders fragment card with filename and atom count', () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'fragment1.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [1, 2],
        mode: 'fragment'
      }
    })

    expect(wrapper.find('.filename').text()).toBe('fragment1.mol')
    expect(wrapper.find('.atom-count').text()).toContain('4')
    expect(wrapper.find('.atom-count').text()).toContain('2')
  })

  it('renders SVG preview with atoms and bonds', () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [],
        mode: 'fragment'
      }
    })

    const svg = wrapper.find('.fragment-svg')
    expect(svg.exists()).toBe(true)
    expect(svg.findAll('.atom-circle')).toHaveLength(4)
    expect(svg.findAll('.bonds line')).toHaveLength(3)
  })

  it('highlights selected atoms with halo', () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [1, 2],
        mode: 'fragment'
      }
    })

    const halos = wrapper.findAll('.selection-halo')
    expect(halos).toHaveLength(2)
  })

  it('displays mode tag with correct color for fragment mode', () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [],
        mode: 'fragment'
      }
    })

    const tag = wrapper.find('.mode-tag')
    expect(tag.attributes('color')).toBe('blue')
  })

  it('displays mode tag with correct color for dock mode', () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [],
        mode: 'dock'
      }
    })

    const tag = wrapper.find('.mode-tag')
    expect(tag.attributes('color')).toBe('orange')
  })

  it('shows selected indices preview when fewer than 6 atoms selected', () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [0, 1, 2],
        mode: 'fragment'
      }
    })

    expect(wrapper.find('.selected-preview').text()).toBe('0, 1, 2')
  })

  it('truncates selected indices preview when more than 5 atoms selected', () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [0, 1, 2, 3, 4, 5, 6],
        mode: 'fragment'
      }
    })

    expect(wrapper.find('.selected-preview').text()).toBe('0, 1, 2...')
  })

  it('emits open-sketch when card is clicked', async () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [],
        mode: 'fragment'
      }
    })

    await wrapper.find('.molecule-inline-fragment-card').trigger('click')
    expect(wrapper.emitted('open-sketch')).toHaveLength(1)
  })

  it('emits open-sketch when button is clicked', async () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [],
        mode: 'fragment'
      }
    })

    await wrapper.find('[data-testid="open-fragment-sketch"]').trigger('click')
    expect(wrapper.emitted('open-sketch')).toHaveLength(1)
  })

  it('does not emit when disabled', async () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [],
        mode: 'fragment',
        disabled: true
      }
    })

    await wrapper.find('.molecule-inline-fragment-card').trigger('click')
    expect(wrapper.emitted('open-sketch')).toBeUndefined()
  })

  it('applies disabled styling when disabled prop is true', () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [],
        mode: 'fragment',
        disabled: true
      }
    })

    expect(wrapper.find('.molecule-inline-fragment-card').classes()).toContain('is-disabled')
  })

  it('renders correctly with no selected atoms', () => {
    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'test.mol',
        atoms: createMockAtoms(),
        bonds: createMockBonds(),
        selectedIndices: [],
        mode: 'fragment'
      }
    })

    expect(wrapper.findAll('.selection-halo')).toHaveLength(0)
    expect(wrapper.find('.selected-preview').exists()).toBe(false)
  })

  it('handles molecules with more than 32 atoms without labels', () => {
    const largeAtoms: InlineFragmentAtom[] = Array.from({ length: 50 }, (_, i) => ({
      index: i,
      element: 'C',
      x2d: i * 0.5,
      y2d: 0,
      isHetero: i % 10 === 0
    }))

    const wrapper = mount(MoleculeInlineFragmentCard, {
      props: {
        filename: 'large.mol',
        atoms: largeAtoms,
        bonds: [],
        selectedIndices: [],
        mode: 'fragment'
      }
    })

    expect(wrapper.findAll('.atom-label')).toHaveLength(0)
  })
})
