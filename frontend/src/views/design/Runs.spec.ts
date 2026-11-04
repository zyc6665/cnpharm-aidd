import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import i18n from '@/locales'

vi.mock('@/api/tasks', () => ({ getTaskList: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }) }))
vi.mock('@/api/projects', () => ({ listProjects: vi.fn().mockResolvedValue({ data: { items: [] } }) }))

const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))

import Runs from './Runs.vue'

const stubs = { RouterLink: { template: '<a><slot /></a>' } }

describe('Runs', () => {
  it('routes to /design from continue button', async () => {
    const w = mount(Runs, { global: { plugins: [i18n], stubs } })
    await new Promise(r => setTimeout(r))
    await w.find('[data-testid="design-runs-continue"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/design')
  })
})
