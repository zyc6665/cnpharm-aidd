import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import i18n from '@/locales'

vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

vi.mock('@ant-design/icons-vue', () => ({
  CopyOutlined: { template: '<span class="copy-icon" />' },
}))

import MoleculeCompareDrawer from './MoleculeCompareDrawer.vue'
import type { CompareMolecule } from './MoleculeCompareDrawer.vue'

const t = i18n.global.t

const molecules: CompareMolecule[] = [
  {
    key: '0',
    index: 1,
    smiles: 'CCO',
    sequence: '',
    rating: 4,
    violations: 0,
    favorite: true,
    metrics: [
      { key: 'mw', label: 'mw', value: '46.07', tone: 'good' },
      { key: 'logp', label: 'logp', value: '780', tone: 'bad' },
    ],
  },
  {
    key: '1',
    index: 2,
    smiles: 'CCN',
    sequence: '',
    rating: null,
    violations: 1,
    metrics: [{ key: 'mw', label: 'mw', value: '45.08', tone: 'good' }],
  },
]

const stubs = {
  'a-drawer': {
    props: ['open', 'title', 'width', 'placement'],
    template: '<div v-if="open" class="a-drawer" :data-title="title"><slot /></div>',
  },
  'a-button': { template: '<button><slot /></button>' },
  'a-rate': { props: ['value', 'disabled'], template: '<span class="a-rate" :data-value="value" />' },
  Smiles2DCell: { props: ['smiles'], template: '<div class="smiles-stub" :data-smiles="smiles" />' },
}

function mountDrawer(open = true, value: CompareMolecule[] = molecules): ReturnType<typeof mount> {
  return mount(MoleculeCompareDrawer, {
    props: { open, molecules: value },
    global: { plugins: [i18n], stubs },
  })
}

describe('MoleculeCompareDrawer', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders one column per molecule with aligned metric rows', () => {
    const wrapper = mountDrawer()

    const columns = wrapper.findAll('[data-testid="molecule-compare-column"]')
    expect(columns).toHaveLength(2)
    expect(columns[0]!.text()).toContain(t('design.results.moleculeIndex', { index: 1 }))
    expect(columns[1]!.text()).toContain(t('design.results.moleculeIndex', { index: 2 }))

    // 第二个分子缺少 logp：该单元格显示空值占位，而不是错位或抛错。
    const mwCells = wrapper.findAll('[data-testid="molecule-compare-metric-mw"]')
    expect(mwCells.map(cell => cell.text())).toEqual(['46.07', '45.08'])
    const logpCells = wrapper.findAll('[data-testid="molecule-compare-metric-logp"]')
    expect(logpCells).toHaveLength(2)
    expect(logpCells[1]!.text()).toBe(t('design.results.compare.noValue'))
  })

  it('applies threshold tones to metric cells', () => {
    const wrapper = mountDrawer()

    const mwCells = wrapper.findAll('[data-testid="molecule-compare-metric-mw"]')
    expect(mwCells[0]!.attributes('data-tone')).toBe('good')

    const logpCells = wrapper.findAll('[data-testid="molecule-compare-metric-logp"]')
    expect(logpCells[0]!.attributes('data-tone')).toBe('bad')
    expect(logpCells[1]!.attributes('data-tone')).toBeUndefined()
  })

  it('shows SMILES, rating, violations and the favorite mark', () => {
    const wrapper = mountDrawer()

    expect(wrapper.findAll('.smiles-stub').map(node => node.attributes('data-smiles'))).toEqual([
      'CCO',
      'CCN',
    ])
    expect(wrapper.findAll('[data-testid="molecule-compare-rating"] a-rate, [data-testid="molecule-compare-rating"] .a-rate')).toHaveLength(1)
    expect(
      wrapper.findAll('[data-testid="molecule-compare-violations"]').map(cell => cell.text())
    ).toEqual(['0', '1'])
    expect(wrapper.findAll('[data-testid="molecule-compare-favorite"]')).toHaveLength(1)
  })

  it('emits update:open when the drawer closes', async () => {
    const wrapper = mountDrawer()

    wrapper.vm.$emit('update:open', false)
    expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
  })

  it('renders an empty hint when there is nothing to compare', () => {
    const wrapper = mountDrawer(true, [])

    expect(wrapper.text()).toContain(t('design.results.compare.empty'))
    expect(wrapper.findAll('[data-testid="molecule-compare-column"]')).toHaveLength(0)
  })
})
