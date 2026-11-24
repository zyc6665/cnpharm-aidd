import { onScopeDispose, getCurrentScope } from 'vue'

export function useRequestSequence(): {
  next(): number
  isCurrent(seq: number): boolean
  invalidate(): void
} {
  let sequence = 0
  const api = {
    next(): number {
      sequence += 1
      return sequence
    },
    isCurrent(seq: number): boolean {
      return sequence === seq
    },
    invalidate(): void {
      sequence += 1
    }
  }
  if (getCurrentScope()) onScopeDispose(api.invalidate)
  return api
}
