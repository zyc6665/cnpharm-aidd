import { getToken } from './request'
import type { AgentEvent } from '@/types/conversations'

export interface AgentStreamOptions {
  afterSequence: number
  signal: AbortSignal
  onEvent: (event: AgentEvent) => void
}

function parseEventFrame(frame: string): AgentEvent | null {
  let id = ''
  let eventType = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator === -1 ? line : line.slice(0, separator)
    const value = separator === -1 ? '' : line.slice(separator + 1).replace(/^ /, '')
    if (field === 'id') id = value
    if (field === 'event') eventType = value
    if (field === 'data') dataLines.push(value)
  }
  if (!dataLines.length) return null
  const payload = JSON.parse(dataLines.join('\n')) as {
    sequence?: number
    event_type?: string
    payload?: Record<string, unknown>
    created_at?: string
    run_id?: string
  }
  const sequence = Number(id || payload.sequence)
  if (!Number.isSafeInteger(sequence) || sequence < 0) return null
  return {
    id: id || String(sequence),
    sequence,
    event_type: payload.event_type || eventType,
    payload: { ...(payload.payload || {}), ...(payload.run_id ? { run_id: payload.run_id } : {}) },
    created_at: payload.created_at,
  }
}

export async function streamAgentRunEvents(runId: string, options: AgentStreamOptions): Promise<void> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  const headers = new Headers({ Accept: 'text/event-stream' })
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.afterSequence > 0) headers.set('Last-Event-ID', String(options.afterSequence))
  const response = await fetch(
    `${baseUrl}/agent-runs/${encodeURIComponent(runId)}/stream?after_sequence=${options.afterSequence}`,
    { headers, signal: options.signal },
  )
  if (!response.ok || !response.body) throw new Error(`事件流连接失败 (${response.status})`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const event = parseEventFrame(buffer.slice(0, boundary))
      buffer = buffer.slice(boundary + 2)
      if (event) options.onEvent(event)
      boundary = buffer.indexOf('\n\n')
    }
    if (done) break
  }
}
