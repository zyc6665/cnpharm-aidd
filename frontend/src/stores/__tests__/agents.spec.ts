import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentsStore } from '@/stores/agents'
import { syncAiddAgentRun } from '@/api/agents'
import type { AiddAgentRun, AiddAgentRunStatus } from '@/types/models'

vi.mock('@/api/agents', () => ({
  cancelAiddAgentRun: vi.fn(),
  createAiddAgentRun: vi.fn(),
  createAiddWorkflowDraft: vi.fn(),
  deleteAiddAgentRun: vi.fn(),
  getAiddAgentRun: vi.fn(),
  getAiddAgentRuns: vi.fn(),
  syncAiddAgentRun: vi.fn()
}))

function makeRun(status: AiddAgentRunStatus): AiddAgentRun {
  return {
    id: 'run-1',
    message: 'Run pocket workflow',
    intent: 'pocket',
    status,
    input_type: 'protein_pdb',
    input_file_id: null,
    input_files: {},
    requested_outputs: [],
    plan: {},
    summary: null,
    error_message: null,
    finished_at: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    steps: []
  }
}

describe('useAgentsStore polling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    vi.mocked(syncAiddAgentRun).mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('轮询失败应记录可见错误，并在连续失败后暂停自动刷新', async () => {
    const store = useAgentsStore()
    vi.mocked(syncAiddAgentRun).mockRejectedValue(new Error('server 500'))

    store.pollRunUntilTerminal('run-1', 10)

    await vi.advanceTimersByTimeAsync(10)
    expect(store.pollError).toBe('server 500')
    expect(store.pollingSuspended).toBe(false)

    await vi.advanceTimersByTimeAsync(20)
    expect(syncAiddAgentRun).toHaveBeenCalledTimes(3)
    expect(store.pollingSuspended).toBe(true)

    await vi.advanceTimersByTimeAsync(30)
    expect(syncAiddAgentRun).toHaveBeenCalledTimes(3)
  })

  it('终态同步成功后应清除轮询错误并停止定时器', async () => {
    const store = useAgentsStore()
    vi.mocked(syncAiddAgentRun).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: makeRun('success')
    })

    store.pollRunUntilTerminal('run-1', 10)

    await vi.advanceTimersByTimeAsync(10)
    expect(store.currentRun?.status).toBe('success')
    expect(store.pollError).toBeNull()
    expect(store.pollingSuspended).toBe(false)

    await vi.advanceTimersByTimeAsync(30)
    expect(syncAiddAgentRun).toHaveBeenCalledTimes(1)
  })
})
