import { ref, onUnmounted } from 'vue'
import { useUserStore } from '@/stores'
import type { WSMessage } from '@/types/models'

type MessageHandler = (message: WSMessage) => void
const DEFAULT_WS_PATH = '/api/v1/ws'

function debugWebSocket(...args: unknown[]) {
  if (import.meta.env.DEV) {
    console.debug('[WebSocket]', ...args)
  }
}

export function useWebSocket() {
  const userStore = useUserStore()

  const ws = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 5
  const reconnectDelay = 3000

  const messageHandlers = ref<MessageHandler[]>([])

  let pingInterval: ReturnType<typeof setInterval> | null = null
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  let currentPath = DEFAULT_WS_PATH

  const getWebSocketUrl = (path: string) => {
    const configuredBaseUrl = import.meta.env.VITE_WS_URL?.trim()
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const baseUrl = configuredBaseUrl
      ? configuredBaseUrl.replace(/\/+$/, '')
      : `${protocol}//${window.location.host}`
    const normalizedPath = path.startsWith('/') ? path : `/${path}`
    return `${baseUrl}${normalizedPath}`
  }

  const connect = (path = DEFAULT_WS_PATH) => {
    if (ws.value?.readyState === WebSocket.OPEN || ws.value?.readyState === WebSocket.CONNECTING) {
      return
    }

    if (!userStore.isLoggedIn) {
      console.warn('[WebSocket] User not logged in, skip connection')
      return
    }

    try {
      currentPath = path
      const url = getWebSocketUrl(path)
      const token = userStore.token ?? ''
      ws.value = new WebSocket(url, token ? ['scitool-access-token', token] : undefined)

      ws.value.onopen = () => {
        debugWebSocket('Connected')
        isConnected.value = true
        reconnectAttempts.value = 0
        startPing()
      }

      ws.value.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WSMessage

          // 处理 pong 消息
          if (message.type === 'pong') {
            return
          }

          // 分发消息给所有处理器
          messageHandlers.value.forEach(handler => {
            try {
              handler(message)
            } catch (err) {
              console.error('[WebSocket] Handler error:', err)
            }
          })
        } catch (err) {
          console.error('[WebSocket] Parse message error:', err)
        }
      }

      ws.value.onerror = (error) => {
        console.error('[WebSocket] Error:', error)
      }

      ws.value.onclose = (event) => {
        debugWebSocket('Closed:', event.code, event.reason)
        isConnected.value = false
        stopPing()

        // 非正常关闭时尝试重连
        if (event.code !== 1000 && reconnectAttempts.value < maxReconnectAttempts) {
          scheduleReconnect()
        }
      }
    } catch (err) {
      console.error('[WebSocket] Connect error:', err)
      scheduleReconnect()
    }
  }

  const disconnect = () => {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout)
      reconnectTimeout = null
    }

    stopPing()

    if (ws.value) {
      ws.value.close(1000, 'Normal closure')
      ws.value = null
    }

    isConnected.value = false
    reconnectAttempts.value = 0
  }

  const send = (data: unknown) => {
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(data))
    } else {
      console.warn('[WebSocket] Not connected, cannot send message')
    }
  }

  const startPing = () => {
    if (pingInterval) return

    pingInterval = setInterval(() => {
      if (ws.value?.readyState === WebSocket.OPEN) {
        send({ action: 'ping' })
      }
    }, 30000) // 每30秒发送一次心跳
  }

  const stopPing = () => {
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
    }
  }

  const scheduleReconnect = () => {
    if (reconnectTimeout) return

    reconnectAttempts.value++
    const delay = reconnectDelay * Math.pow(2, reconnectAttempts.value - 1) // 指数退避

    debugWebSocket(
      `Reconnecting in ${delay}ms (attempt ${reconnectAttempts.value}/${maxReconnectAttempts})`
    )

    reconnectTimeout = setTimeout(() => {
      reconnectTimeout = null
      connect(currentPath)
    }, delay)
  }

  const onMessage = (handler: MessageHandler) => {
    messageHandlers.value.push(handler)

    // 返回取消订阅函数
    return () => {
      const index = messageHandlers.value.indexOf(handler)
      if (index > -1) {
        messageHandlers.value.splice(index, 1)
      }
    }
  }

  // 订阅特定任务
  const subscribeTask = (taskId: string) => {
    send({ action: 'subscribe_task', task_id: taskId })
  }

  // 取消订阅特定任务
  const unsubscribeTask = (taskId: string) => {
    send({ action: 'unsubscribe_task', task_id: taskId })
  }

  // 组件卸载时自动清理
  onUnmounted(() => {
    disconnect()
  })

  return {
    isConnected,
    connect,
    disconnect,
    send,
    onMessage,
    subscribeTask,
    unsubscribeTask
  }
}
