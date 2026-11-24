import { effectScope, nextTick, ref, watch } from 'vue'
import { describe, expect, it } from 'vitest'
import { useRequestSequence } from './useRequestSequence'

describe('useRequestSequence', () => {
  it('suppresses a stale A response after A -> B -> A', () => {
    const sequence = useRequestSequence()
    const firstA = sequence.next()
    const b = sequence.next()
    const secondA = sequence.next()

    expect(sequence.isCurrent(firstA)).toBe(false)
    expect(sequence.isCurrent(b)).toBe(false)
    expect(sequence.isCurrent(secondA)).toBe(true)
  })

  it('invalidates the current request explicitly', () => {
    const sequence = useRequestSequence()
    const current = sequence.next()
    sequence.invalidate()

    expect(sequence.isCurrent(current)).toBe(false)
  })

  it('invalidates requests when the owning effect scope is disposed', async () => {
    const value = ref(0)
    let isCurrent: ((seq: number) => boolean) | undefined
    let currentSeq = 0
    const scope = effectScope()
    scope.run(() => {
      const sequence = useRequestSequence()
      currentSeq = sequence.next()
      isCurrent = sequence.isCurrent
      watch(value, () => sequence.next())
    })

    value.value = 1
    await nextTick()
    expect(isCurrent?.(currentSeq)).toBe(false)
    currentSeq = 2
    scope.stop()
    expect(isCurrent?.(currentSeq)).toBe(false)
  })
})
