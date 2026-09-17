import { nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { Tool } from '@/types/models'
import { useWorkflowNodeSelectedTool } from './useWorkflowNodeSelectedTool'

function makeTool(id: string, slug: string): Tool {
  return {
    id,
    slug,
    name: slug,
    description: 'Tool detail',
    category: 'AIDD',
    tags: [],
    status: 'published',
    usage_count: 0,
    view_count: 0,
    favorite_count: 0,
    gpu_required: false,
    created_at: '2026-09-17T00:00:00Z',
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(innerResolve => {
    resolve = innerResolve
  })
  return { promise, resolve }
}

async function flushAsync() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
}

describe('useWorkflowNodeSelectedTool', () => {
  it('loads tool detail for the selected available tool', async () => {
    const api = {
      getToolDetail: vi.fn().mockResolvedValue(makeTool('tool-1', 'builtin-fetch-pdb')),
    }

    const state = useWorkflowNodeSelectedTool({
      selectedToolSlug: ref('builtin-fetch-pdb'),
      availableTools: ref([
        { id: 'tool-1', slug: 'builtin-fetch-pdb', name: 'Fetch PDB Structure' },
      ]),
      api,
      onMissingTool: vi.fn(),
    })

    expect(state.selectedToolLoading.value).toBe(true)
    await flushAsync()

    expect(api.getToolDetail).toHaveBeenCalledWith('tool-1')
    expect(state.selectedTool.value).toMatchObject({ id: 'tool-1', slug: 'builtin-fetch-pdb' })
    expect(state.selectedToolLoading.value).toBe(false)
  })

  it('clears selected tool state when the selected slug has no concrete id', async () => {
    const onMissingTool = vi.fn()
    const api = { getToolDetail: vi.fn() }

    const state = useWorkflowNodeSelectedTool({
      selectedToolSlug: ref('builtin-fetch-pdb'),
      availableTools: ref([{ slug: 'builtin-fetch-pdb', name: 'Fetch PDB Structure' }]),
      api,
      onMissingTool,
    })

    await flushAsync()

    expect(api.getToolDetail).not.toHaveBeenCalled()
    expect(state.selectedTool.value).toBeNull()
    expect(state.selectedToolLoading.value).toBe(false)
    expect(onMissingTool).toHaveBeenCalledTimes(1)
  })

  it('ignores stale detail responses after the selected tool changes', async () => {
    const first = deferred<Tool>()
    const second = deferred<Tool>()
    const selectedToolSlug = ref('tool-a')
    const api = {
      getToolDetail: vi.fn((toolId: string) => (
        toolId === 'tool-a-id' ? first.promise : second.promise
      )),
    }
    const state = useWorkflowNodeSelectedTool({
      selectedToolSlug,
      availableTools: ref([
        { id: 'tool-a-id', slug: 'tool-a', name: 'Tool A' },
        { id: 'tool-b-id', slug: 'tool-b', name: 'Tool B' },
      ]),
      api,
      onMissingTool: vi.fn(),
    })

    selectedToolSlug.value = 'tool-b'
    await nextTick()

    second.resolve(makeTool('tool-b-id', 'tool-b'))
    await flushAsync()
    first.resolve(makeTool('tool-a-id', 'tool-a'))
    await flushAsync()

    expect(api.getToolDetail).toHaveBeenCalledWith('tool-a-id')
    expect(api.getToolDetail).toHaveBeenCalledWith('tool-b-id')
    expect(state.selectedTool.value).toMatchObject({ id: 'tool-b-id', slug: 'tool-b' })
    expect(state.selectedToolLoading.value).toBe(false)
  })
})
