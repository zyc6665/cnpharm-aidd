import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import SequenceSelectorBar from './SequenceSelectorBar.vue'
import type { SequenceChain } from '@/domain/tasks'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params?.count !== undefined ? `${key}:${params.count}` : key,
  }),
}))

const chains: SequenceChain[] = [
  {
    chain: 'A',
    residues: [
      { key: 'A:1', chain: 'A', seqId: 1, compId: 'MET', oneLetter: 'M' },
      { key: 'A:10', chain: 'A', seqId: 10, compId: 'ALA', oneLetter: 'A' },
    ],
  },
  {
    chain: 'B',
    residues: [
      { key: 'B:5', chain: 'B', seqId: 5, compId: 'GLY', oneLetter: 'G' },
    ],
  },
]

describe('SequenceSelectorBar', () => {
  it('renders chains, switches chain tabs, and emits toggle-residue with shiftKey', async () => {
    const wrapper = mount(SequenceSelectorBar, {
      props: {
        chains,
        selectedKeys: ['A:10'],
        theme: 'white',
      },
    })

    expect(wrapper.find('.sequence-bar--white').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid="sequence-chain-tab"]')).toHaveLength(2)
    expect(wrapper.get('[data-testid="sequence-selected-count"]').text()).toContain('1')

    const residueButtons = wrapper.findAll('[data-testid="sequence-residue-btn"]')
    expect(residueButtons).toHaveLength(2)
    expect(residueButtons[1]!.classes()).toContain('is-selected')

    await residueButtons[0]!.trigger('click', { shiftKey: true })
    expect(wrapper.emitted('toggle-residue')?.[0]).toEqual([
      { chain: 'A', seqId: 1, shiftKey: true },
    ])

    await wrapper.findAll('[data-testid="sequence-chain-tab"]')[1]!.trigger('click')
    expect(wrapper.findAll('[data-testid="sequence-residue-btn"]')).toHaveLength(1)
    expect(wrapper.get('[data-testid="sequence-residue-btn"]').text()).toBe('G')
  })

  it('emits focus-selection, clear-selection, and close events', async () => {
    const wrapper = mount(SequenceSelectorBar, {
      props: {
        chains,
        selectedKeys: ['A:1'],
      },
    })

    await wrapper.get('[data-testid="sequence-focus-btn"]').trigger('click')
    await wrapper.get('[data-testid="sequence-clear-btn"]').trigger('click')
    await wrapper.get('[data-testid="sequence-close-btn"]').trigger('click')

    expect(wrapper.emitted('focus-selection')).toHaveLength(1)
    expect(wrapper.emitted('clear-selection')).toHaveLength(1)
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
