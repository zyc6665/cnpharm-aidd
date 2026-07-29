import { beforeEach, expect, test, vi } from 'vitest'
import { getToolList } from '@/api/tools'
import { useRemoteToolOptions } from '@/composables/useRemoteToolOptions'
import type { Tool } from '@/types/models'

vi.mock('@/api/tools', () => ({
  getToolList: vi.fn()
}))

const mockedGetToolList = vi.mocked(getToolList)

function tool(id: string, name: string): Tool {
  return {
    id,
    name,
    slug: id,
    tags: [],
    status: 'published',
    usage_count: 0,
    view_count: 0,
    favorite_count: 0,
    gpu_required: false,
    created_at: '2026-07-29T00:00:00Z'
  }
}

function response(items: Tool[]) {
  return {
    code: 200,
    message: 'success',
    data: {
      items,
      total: items.length,
      page: 1,
      page_size: 50,
      total_pages: items.length ? 1 : 0
    }
  }
}

beforeEach(() => {
  mockedGetToolList.mockReset()
})

test('远程工具选项应把规范化关键词传给服务端', async () => {
  mockedGetToolList.mockResolvedValue(response([tool('alpha', 'Alpha')]))
  const { fetchToolOptions, toolOptions } = useRemoteToolOptions()

  await fetchToolOptions('  alpha  ')

  expect(mockedGetToolList).toHaveBeenCalledWith({
    page: 1,
    page_size: 50,
    search: 'alpha'
  })
  expect(toolOptions.value.map(item => item.id)).toEqual(['alpha'])
})

test('较慢的旧查询不应覆盖较新的工具选项', async () => {
  let resolveOld: ((value: ReturnType<typeof response>) => void) | undefined
  mockedGetToolList
    .mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveOld = resolve
        })
    )
    .mockResolvedValueOnce(response([tool('new', 'New')]))
  const { fetchToolOptions, toolOptions, toolOptionsLoading } = useRemoteToolOptions()

  const oldRequest = fetchToolOptions('old')
  await fetchToolOptions('new')
  resolveOld?.(response([tool('old', 'Old')]))
  await oldRequest

  expect(toolOptions.value.map(item => item.id)).toEqual(['new'])
  expect(toolOptionsLoading.value).toBe(false)
})
