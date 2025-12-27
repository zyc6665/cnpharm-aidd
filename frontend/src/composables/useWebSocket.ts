import { ref, onUnmounted } from 'vue'
import { useUserStore } from '@/stores'
import type { WSMessage } from '@/types/models'

type MessageHandler = (message: WSMessage) => void

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

  const getWebSocketUrl = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = import.meta.env.VITE_WS_HOST || window.location.host
    const token = userStore.token
    return `${protocol}//${host}/api/v1/ws?token=${token}`
  }

  const connect = () => {
    if (ws.value?.readyState === WebSocket.OPEN) {
      return
    }

    if (!userStore.isLoggedIn) {
      console.warn('[WebSocket] User not logged in, skip connection')
      return
    }

    try {
      const url = getWebSocketUrl()
      ws.value = new WebSocket(url)

      ws.value.onopen = () => {
        console.log('[WebSocket] Connected')
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
        console.log('[WebSocket] Closed:', event.code, event.reason)
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
        send({ type: 'ping' })
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

    console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.value}/${maxReconnectAttempts})`)

    reconnectTimeout = setTimeout(() => {
      reconnectTimeout = null
      connect()
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
    send({ type: 'subscribe', task_id: taskId })
  }

  // 取消订阅特定任务
  const unsubscribeTask = (taskId: string) => {
    send({ type: 'unsubscribe', task_id: taskId })
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
