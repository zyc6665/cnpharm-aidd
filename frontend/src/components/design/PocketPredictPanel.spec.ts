import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import i18n from '@/locales'

vi.mock('@/api/targets', () => ({
  listPockets: vi.fn().mockResolvedValue({ data: { items: [] } }),
  selectPocket: vi.fn(),
  predictPockets: vi.fn().mockResolvedValue({ data: { task_id: 't1' } }),
}))
vi.mock('@/composables/useTaskCompletion', () => ({
  waitForTaskCompletion: vi.fn().mockResolvedValue({ status: 'failure', ok: false }),
}))

import PocketPredictPanel from './PocketPredictPanel.vue'

const stubs = {
  'a-alert': { props: ['message'], template: '<div class="stub-alert">{{ message }}</div>' },
}

describe('PocketPredictPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows an error when the prediction task fails instead of staying silent', async () => {
    const w = mount(PocketPredictPanel, { props: { structureId: 's1' }, global: { plugins: [i18n], stubs } })
    await flushPromises()
    await w.find('[data-testid="pocket-predict-button"]').trigger('click')
    await flushPromises()
    await new Promise(r => setTimeout(r))
    await flushPromises()
    expect(w.text()).toContain('口袋预测任务提交失败')
  })
})
