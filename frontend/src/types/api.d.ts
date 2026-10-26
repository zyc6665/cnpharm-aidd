// API 响应类型
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

export interface ApiError {
  code: number
  message: string
  detail?: string
}

// 环境变量类型
//
// 步骤 9 已用 SSE 替换 WebSocket，原来的 WS 地址变量不再有消费方，故不再声明。
// 声明一个没人读的环境变量只会让人以为还存在 WS 通道。
interface ImportMetaEnv {
  readonly VITE_APP_TITLE: string
  readonly VITE_API_BASE_URL: string
  readonly VITE_APP_ENV: 'development' | 'production'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
