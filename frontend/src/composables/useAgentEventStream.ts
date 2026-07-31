import { onBeforeUnmount, ref } from 'vue'
import { streamAgentRunEvents } from '@/api/agent-stream'
import { useProjectConversationStore } from '@/stores/project-conversation'

interface AgentEventStreamConfig {
  reconnectDelayMs?: number
}

const TERMINAL_EVENT_TYPES = new Set([
  'analysis_summary',
  'execution_completed',
  'execution_failed',
  'input_required',
  'run_canceled',
])

export function useAgentEventStream(config: AgentEventStreamConfig = {}) {
  const store = useProjectConversationStore()
  const connected = ref(false)
  const reconnecting = ref(false)
  const error = ref<string | null>(null)
  const reconnectDelayMs = config.reconnectDelayMs ?? 1500
  let runId: string | null = null
  let controller: AbortController | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let generation = 0
  let lastConnectedRunId: string | null = null

  function disconnect() {
    generation += 1
    runId = null
    controller?.abort()
    controller = null
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = null
    connected.value = false
    reconnecting.value = false
  }

  async function open(activeGeneration: number) {
    if (!runId || activeGeneration !== generation) return
    controller = new AbortController()
    try {
      connected.value = true
      reconnecting.value = false
      error.value = null
      await streamAgentRunEvents(runId, {
        afterSequence: store.lastSequence,
        signal: controller.signal,
        onEvent: store.applyEvent,
      })
    } catch (reason) {
      if (controller.signal.aborted || activeGeneration !== generation) return
      error.value = reason instanceof Error ? reason.message : '事件流连接失败'
    } finally {
      connected.value = false
    }
    if (!runId || activeGeneration !== generation) return
    const lastEvent = store.events[store.events.length - 1]
    if (lastEvent && TERMINAL_EVENT_TYPES.has(lastEvent.event_type)) return
    reconnecting.value = true
    reconnectTimer = setTimeout(() => void open(activeGeneration), reconnectDelayMs)
  }

  function connect(nextRunId: string) {
    const previousRunId = lastConnectedRunId
    disconnect()
    if (previousRunId && previousRunId !== nextRunId) store.resetEvents()
    runId = nextRunId
    lastConnectedRunId = nextRunId
    const activeGeneration = generation
    void open(activeGeneration)
  }

  onBeforeUnmount(disconnect)
  return { connected, reconnecting, error, connect, disconnect }
}
