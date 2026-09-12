import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { streamAgentRunEvents } from '@/api/agent-stream'
import { useProjectConversationStore } from '@/stores/project-conversation'
import { useAgentEventStream } from './useAgentEventStream'

vi.mock('@/api/agent-stream', () => ({ streamAgentRunEvents: vi.fn() }))

describe('useAgentEventStream', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  it('仅将递增 sequence 事件交给集中 reducer', async () => {
    vi.mocked(streamAgentRunEvents).mockImplementation(async (_runId, options) => {
      options.onEvent({ id: '1', sequence: 1, event_type: 'thinking', payload: {} })
      options.onEvent({ id: '1-copy', sequence: 1, event_type: 'thinking', payload: {} })
      options.onEvent({ id: '2', sequence: 2, event_type: 'execution_progress', payload: { progress: 30 } })
    })
    const store = useProjectConversationStore()
    const stream = useAgentEventStream({ reconnectDelayMs: 10 })

    stream.connect('run-1')
    await vi.advanceTimersByTimeAsync(0)

    expect(store.events.map(event => event.sequence)).toEqual([1, 2])
    expect(store.lastSequence).toBe(2)
    stream.disconnect()
  })

  it('断线后携带最后 sequence 重连', async () => {
    let releaseSecondConnection!: () => void
    vi.mocked(streamAgentRunEvents)
      .mockImplementationOnce(async (_runId, options) => {
        options.onEvent({ id: '7', sequence: 7, event_type: 'thinking', payload: {} })
      })
      .mockImplementationOnce(
        () => new Promise<void>(resolve => {
          releaseSecondConnection = resolve
        }),
      )
    const stream = useAgentEventStream({ reconnectDelayMs: 10 })

    stream.connect('run-1')
    await vi.advanceTimersByTimeAsync(10)

    expect(streamAgentRunEvents).toHaveBeenNthCalledWith(
      2,
      'run-1',
      expect.objectContaining({ afterSequence: 7 }),
    )
    stream.disconnect()
    releaseSecondConnection()
  })

  it('切换到新 Run 时清空旧事件并从 sequence 0 连接', async () => {
    vi.mocked(streamAgentRunEvents).mockImplementation(async (_runId, options) => {
      options.onEvent({ id: '4', sequence: 4, event_type: 'thinking', payload: {} })
    })
    const stream = useAgentEventStream({ reconnectDelayMs: 10 })

    stream.connect('run-1')
    await vi.advanceTimersByTimeAsync(0)
    stream.disconnect()
    stream.connect('run-2')
    await vi.advanceTimersByTimeAsync(0)

    expect(streamAgentRunEvents).toHaveBeenLastCalledWith(
      'run-2',
      expect.objectContaining({ afterSequence: 0 }),
    )
    stream.disconnect()
  })

  it('收到终态事件后不再重连', async () => {
    vi.mocked(streamAgentRunEvents).mockImplementation(async (_runId, options) => {
      options.onEvent({ id: '1', sequence: 1, event_type: 'analysis_summary', payload: {} })
    })
    const stream = useAgentEventStream({ reconnectDelayMs: 10 })

    stream.connect('run-1')
    await vi.advanceTimersByTimeAsync(50)

    expect(streamAgentRunEvents).toHaveBeenCalledTimes(1)
    stream.disconnect()
  })
})
