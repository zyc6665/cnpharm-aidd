import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { parseFragmentMolecule } from '@/domain/molecules/fragment-graph'
import { SAMPLE_LIGAND_SDF } from '@/domain/molecules/sample-inputs'
import FragmentSketchModal from './FragmentSketchModal.vue'

const molecule = parseFragmentMolecule(SAMPLE_LIGAND_SDF, 'ligand.sdf')!
const id = (suffix: string | number) => `[data-testid="sketch-${suffix}"]`
const atom = (index: number) => id(`atom-${index}`)

function render(mode: 'fragment' | 'dock' = 'fragment', selectedIndices: number[] = []) {
  return mount(FragmentSketchModal, {
    props: { open: true, molecule, mode, selectedIndices },
    global: {
      plugins: [createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': {} } })],
      stubs: {
        'a-modal': { props: ['open', 'title'], template: '<div v-if="open"><h2>{{ title }}</h2><slot /><slot name="footer" /></div>' },
        'a-button': { props: ['type', 'size', 'shape'], template: '<button type="button"><slot /></button>' }
      }
    }
  })
}

describe('FragmentSketchModal', () => {
  it('previews the initial selection and edits it by mouse, keyboard, and remove pill', async () => {
    const wrapper = render('fragment', [0, 14, 0])
    expect(wrapper.get(id('count')).text()).toBe('已选原子：1 / 13')
    expect(wrapper.get(atom(0)).attributes('aria-pressed')).toBe('true')
    await wrapper.get(atom(2)).trigger('click')
    await wrapper.get(atom(4)).trigger('keydown', { key: 'Enter' })
    await wrapper.get(id('remove-0')).trigger('click')
    expect(wrapper.get(id('preview-canvas')).findAll('.sketch-atom.is-selected')).toHaveLength(2)
    expect(wrapper.get(id('count')).text()).toBe('已选原子：2 / 13')
    await wrapper.get(id('confirm')).trigger('click')
    expect(wrapper.emitted('confirm')).toEqual([[{ selectedIndices: [2, 4], exportedFile: expect.any(File) }]])
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('expands the smallest ring and confirms only indices in dock mode', async () => {
    const wrapper = render('dock')
    expect(wrapper.text()).toContain('atoms_to_dock')
    await wrapper.get(id('tool-ring')).trigger('click')
    await wrapper.get(atom(8)).trigger('click')
    expect(wrapper.get(id('count')).text()).toBe('已选原子：3 / 13')
    await wrapper.get(id('confirm')).trigger('click')
    expect(wrapper.emitted('confirm')).toEqual([[{ selectedIndices: [8, 9, 10], exportedFile: null }]])
  })

  it('keeps edits local on cancel, restores the prop when reopened, and reuses the input at full selection', async () => {
    const wrapper = render('fragment', [5])
    const click = (text: string) => wrapper.findAll('button').find(button => button.text() === text)!.trigger('click')
    await click('反选')
    expect(wrapper.get(id('count')).text()).toBe('已选原子：12 / 13')
    await click('清空')
    expect(wrapper.get(id('confirm')).attributes('disabled')).toBeDefined()
    await click('取消')
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.emitted('update:open')).toEqual([[false]])
    await wrapper.setProps({ open: false })
    await wrapper.setProps({ open: true })
    expect(wrapper.get(id('count')).text()).toBe('已选原子：1 / 13')
    await click('全选')
    await wrapper.get(id('confirm')).trigger('click')
    expect(wrapper.emitted('confirm')).toEqual([[{ selectedIndices: molecule.atoms.map(atom => atom.index), exportedFile: null }]])
  })

  it('adds atoms inside a marquee in SVG coordinates and clears the overlay', async () => {
    const wrapper = render('dock', [0])
    const canvas = wrapper.get<SVGSVGElement>(id('editor-canvas'))
    const screenMatrix = { inverse: () => ({}) }
    Object.assign(canvas.element, {
      getScreenCTM: () => screenMatrix,
      createSVGPoint: () => ({ x: 0, y: 0, matrixTransform() { return { x: this.x / 2, y: this.y / 2 } } }),
      setPointerCapture: vi.fn()
    })
    const [, x, y] = wrapper.get(atom(2)).attributes('transform')!.match(/^translate\((\S+) (\S+)\)$/)!
    const [cx, cy] = [Number(x), Number(y)]
    const pointer = async (name: string, dx: number, dy: number) => {
      const event = new MouseEvent(name, { clientX: (cx + dx) * 2, clientY: (cy + dy) * 2, button: 0, bubbles: true })
      Object.defineProperty(event, 'pointerId', { value: 7 })
      canvas.element.dispatchEvent(event)
      await wrapper.vm.$nextTick()
    }
    await wrapper.get(id('tool-box')).trigger('click')
    await pointer('pointerdown', 4, 4)
    await pointer('pointermove', -4, -4)
    expect(canvas.find('.sketch-marquee').exists()).toBe(true)
    await pointer('pointerup', -4, -4)
    expect(canvas.find('.sketch-marquee').exists()).toBe(false)
    await wrapper.get(id('confirm')).trigger('click')
    expect(wrapper.emitted('confirm')).toEqual([[{ selectedIndices: [0, 2], exportedFile: null }]])
  })

  it('zooms just the editor and restores the initial viewport', async () => {
    const wrapper = render()
    const canvas = wrapper.get(id('editor-canvas'))
    const initial = canvas.attributes('viewBox')
    await wrapper.get('button[aria-label="放大"]').trigger('click')
    expect(canvas.attributes('viewBox')).not.toBe(initial)
    expect(wrapper.get(id('preview-canvas')).attributes('viewBox')).toBe(initial)
    await wrapper.findAll('button').find(button => button.text() === '重置视图')!.trigger('click')
    expect(canvas.attributes('viewBox')).toBe(initial)
  })
})
