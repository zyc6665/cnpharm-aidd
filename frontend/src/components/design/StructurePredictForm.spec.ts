import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import i18n from '@/locales'

vi.mock('@/api/targets', () => ({ predictStructure: vi.fn() }))
vi.mock('@/composables/useTaskCompletion', () => ({ waitForTaskCompletion: vi.fn() }))

import { predictStructure } from '@/api/targets'
import { waitForTaskCompletion } from '@/composables/useTaskCompletion'
import StructurePredictForm from './StructurePredictForm.vue'

describe('StructurePredictForm', () => {
  beforeEach(() => {
    vi.mocked(predictStructure).mockReset()
    vi.mocked(waitForTaskCompletion).mockReset()
  })

  it('emits a friendly error when the prediction task fails', async () => {
    vi.mocked(predictStructure).mockResolvedValue({ data: { task_id: 't1' } } as never)
    vi.mocked(waitForTaskCompletion).mockResolvedValue({ status: 'failure', ok: false } as never)
    const w = mount(StructurePredictForm, { props: { proteinId: 'p1' }, global: { plugins: [i18n] } })
    await w.find('[data-testid="structure-predict-submit"]').trigger('click')
    await flushPromises()
    await new Promise(r => setTimeout(r))
    await flushPromises()
    const events = w.emitted('error')
    expect(events?.length).toBe(1)
    expect(events![0]![0]).toBe('结构预测任务提交失败')
  })
})
