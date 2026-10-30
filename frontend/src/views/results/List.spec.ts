import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ResultsList from './List.vue'
import { listProjectResults } from '@/api/results'

vi.mock('@/api/results', () => ({
  listProjectResults: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'project-1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() })
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params && 'total' in params ? `${key}:${String(params.total)}` : key
  })
}))

function renderList() {
  return mount(ResultsList, {
    global: {
      stubs: {
        ProjectWorkspaceNav: true,
        SkeletonList: true,
        AppPageHeader: { template: '<div><slot name="actions" /></div>' },
        RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
        AAlert: { template: '<div><slot /></div>' },
        AButton: {
          props: ['loading'],
          emits: ['click'],
          template: '<button :disabled="loading" @click="$emit(\'click\')"><slot /></button>'
        },
        ATag: true,
        ASelect: {
          props: ['value'],
          emits: ['change'],
          template: '<div @click="$emit(\'change\')" />'
        },
        'a-select': {
          props: ['value'],
          emits: ['change'],
          template: '<div @click="$emit(\'change\')" />'
        },
        ATable: {
          props: ['dataSource'],
          template:
            '<div class="fake-table"><div v-for="row in dataSource" :key="row.task_id" class="fake-row">{{ row.name || row.task_id }}</div></div>'
        }
      }
    }
  })
}

function rowTexts(wrapper: ReturnType<typeof renderList>): string[] {
  return wrapper.findAll('.fake-row').map(row => row.text())
}

describe('ResultsList 游标加载更多', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('首屏 offset 拿到 nextCursor 后加载更多并去重，到底显示已全部加载', async () => {
    vi.mocked(listProjectResults)
      .mockResolvedValueOnce({
        data: {
          items: [{ task_id: 't1', name: 'Alpha', finished_at: '2026-01-01T00:00:00Z' }],
          total: 3,
          page: 1,
          page_size: 20,
          total_pages: 1,
          nextCursor: 'cursor-2',
          hasMore: true,
          totalKnown: true
        }
      } as never)
      .mockResolvedValueOnce({
        data: {
          // 第二页故意重复 t1，验证按 task_id 去重。
          items: [
            { task_id: 't2', name: 'Beta', finished_at: '2026-01-02T00:00:00Z' },
            { task_id: 't1', name: 'Alpha', finished_at: '2026-01-01T00:00:00Z' }
          ],
          total: null,
          page: null,
          page_size: 20,
          total_pages: null,
          nextCursor: null,
          hasMore: false,
          totalKnown: false
        }
      } as never)

    const wrapper = renderList()
    await flushPromises()

    expect(listProjectResults).toHaveBeenNthCalledWith(1, 'project-1', {
      page: 1,
      page_size: 20
    })
    expect(rowTexts(wrapper)).toEqual(['Alpha'])
    const loadMore = wrapper.find('[data-testid="results-load-more"]')
    expect(loadMore.exists()).toBe(true)

    await loadMore.trigger('click')
    await flushPromises()

    expect(listProjectResults).toHaveBeenNthCalledWith(2, 'project-1', {
      page_size: 20,
      cursor: 'cursor-2'
    })
    // 追加且去重：t1 不重复；列表按 finished_at 倒序，Beta(01-02) 在 Alpha(01-01) 前。
    expect(rowTexts(wrapper)).toEqual(['Beta', 'Alpha'])
    expect(wrapper.find('[data-testid="results-load-more"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="results-all-loaded"]').exists()).toBe(true)
  })

  it('切换筛选时重置游标与列表', async () => {
    vi.mocked(listProjectResults)
      .mockResolvedValueOnce({
        data: {
          items: [{ task_id: 't1', name: 'Alpha', finished_at: '2026-01-01T00:00:00Z' }],
          total: 2,
          page: 1,
          page_size: 20,
          total_pages: 1,
          nextCursor: 'cursor-2',
          hasMore: true,
          totalKnown: true
        }
      } as never)
      .mockResolvedValueOnce({
        data: {
          items: [{ task_id: 't3', name: 'Gamma', finished_at: '2026-01-03T00:00:00Z' }],
          total: 1,
          page: 1,
          page_size: 20,
          total_pages: 1,
          nextCursor: null,
          hasMore: false,
          totalKnown: true
        }
      } as never)

    const wrapper = renderList()
    await flushPromises()
    expect(rowTexts(wrapper)).toEqual(['Alpha'])

    await wrapper.find('[data-testid="results-status-filter"]').trigger('click')
    await flushPromises()

    expect(listProjectResults).toHaveBeenCalledTimes(2)
    expect(rowTexts(wrapper)).toEqual(['Gamma'])
    expect(wrapper.find('[data-testid="results-all-loaded"]').exists()).toBe(true)
  })
})
