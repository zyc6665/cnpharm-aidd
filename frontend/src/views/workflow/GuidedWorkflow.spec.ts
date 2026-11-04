import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import i18n from '@/locales'

vi.mock('@/api/targets', () => ({
  listTargets: vi.fn().mockResolvedValue({ data: { items: [{ id: 't1' }] } }),
  getTarget: vi.fn().mockResolvedValue({ data: { proteins: [{ id: 'pr1' }] } }),
  listStructures: vi.fn().mockResolvedValue({ data: { items: [{ id: 's1' }] } }),
  listPockets: vi.fn().mockResolvedValue({ data: { items: [] } }),
}))
vi.mock('@/api/compounds', () => ({ listCandidates: vi.fn().mockResolvedValue({ data: { total: 0 } }) }))
vi.mock('@/api/results', () => ({ listProjectResults: vi.fn().mockResolvedValue({ data: { total: 0 } }) }))

import GuidedWorkflow from './GuidedWorkflow.vue'

describe('GuidedWorkflow', () => {
  it('embeds the structure predict form instead of a link-out button', async () => {
    const w = mount(GuidedWorkflow, { props: { projectId: 'p1' }, global: { plugins: [i18n] } })
    await new Promise(r => setTimeout(r))
    expect(w.find('[data-testid="structure-predict-form"]').exists()).toBe(true)
    expect(w.text()).not.toContain('去结构预测')
  })
})
