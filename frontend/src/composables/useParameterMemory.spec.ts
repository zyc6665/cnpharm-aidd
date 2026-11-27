import { describe, expect, it, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useUserStore } from '@/stores/user'
import { useParameterMemory } from './useParameterMemory'
import type { ToolSchema } from '@/types/models'

const sampleSchema: ToolSchema = {
  type: 'object',
  properties: {
    nsteps: { type: 'integer', default: 2500, minimum: 0, maximum: 5000000 },
    water_model: { type: 'string', enum: ['tip3p', 'spc', 'tip4p'], default: 'tip3p' },
    sequence: { type: 'string', default: '' },
  },
}

describe('useParameterMemory', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('scopes storage key by user id and filters omitted/unknown keys', () => {
    const userStore = useUserStore()
    userStore.userInfo = { id: 'user-a', username: 'a', email: 'a@x.local', role: 'user', status: 'active' } as never

    const slug = ref('gromacs-md')
    const schema = ref<ToolSchema | null>(sampleSchema)
    const memory = useParameterMemory({ scope: 'md', slug, schema, omitKeys: ['sequence'] })

    expect(memory.storageKey.value).toBe('design:u:user-a:params:md:gromacs-md')

    memory.persist({ nsteps: 50000, water_model: 'tip4p', sequence: 'ACDE', stale_key: 123 })
    const restored = memory.restore()
    expect(restored.restoredFromMemory).toBe(true)
    expect(restored.diffKeys).toEqual(['nsteps', 'water_model'])
    expect(restored.values).toEqual({ nsteps: 50000, water_model: 'tip4p' })

    // Switching user isolates stored memory
    userStore.userInfo = { id: 'user-b', username: 'b', email: 'b@x.local', role: 'user', status: 'active' } as never
    const otherUser = memory.restore()
    expect(otherUser.restoredFromMemory).toBe(false)
    expect(otherUser.values).toEqual({ nsteps: 2500, water_model: 'tip3p' })
  })

  it('clears stored entry and handles storage errors gracefully', () => {
    const slug = ref('gromacs-md')
    const schema = ref<ToolSchema | null>(sampleSchema)
    const memory = useParameterMemory({ scope: 'md', slug, schema })
    memory.persist({ nsteps: 10000 })
    expect(memory.restore().restoredFromMemory).toBe(true)
    memory.clear()
    expect(memory.restore().restoredFromMemory).toBe(false)

    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(memory.persist({ nsteps: 10000 })).toBe(false)
    spy.mockRestore()
  })

  it('uses structural equality for default comparisons and drops incompatible schema versions', () => {
    const schemaWithArray = ref<ToolSchema | null>({
      type: 'object',
      properties: {
        targets: { type: 'array', default: ['A', 'B'] },
        water_model: { type: 'string', enum: ['tip3p', 'spc', 'tip4p'], default: 'tip3p' },
      },
    })
    const slug = ref('array-tool')
    const memory = useParameterMemory({ scope: 'test', slug, schema: schemaWithArray })

    memory.persist({ targets: ['A', 'B'] as never, water_model: 'tip3p' })
    const sameDefaults = memory.restore()
    expect(sameDefaults.diffKeys).toEqual([])
    expect(sameDefaults.restoredFromMemory).toBe(false)

    // Type mismatch / enum mismatch is filtered out
    localStorage.setItem(
      memory.storageKey.value,
      JSON.stringify({ v: 1, params: { targets: 'not-an-array', water_model: 'bad-water' } })
    )
    expect(memory.restore().values).toEqual({ targets: ['A', 'B'], water_model: 'tip3p' })

    // Schema change invalidates old fingerprint
    const changedSchema: ToolSchema = {
      type: 'object',
      properties: {
        targets: { type: 'array', default: ['A', 'B'] },
        water_model: { type: 'integer', default: 1 },
      },
    }
    expect(memory.restore(changedSchema).restoredFromMemory).toBe(false)
  })
})
