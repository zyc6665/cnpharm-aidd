import axios, { type AxiosInstance, type AxiosRequestConfig, AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { message } from 'ant-design-vue'
import type { ApiResponse, ApiError } from '@/types/api'
import { shouldAttemptTokenRefresh } from './auth-request-policy'
import { applySessionInvalid, readErrorReason, rememberRefreshFailure } from './sso-session'
import { clearAuthStorage } from '@/utils/auth-storage'
import { buildCsrfHeader } from '@/utils/cookies'

export interface RequestOptions extends AxiosRequestConfig {
  silent?: boolean
  retry?: number
  retryDelayMs?: number
  /** 启动恢复会话等场景：刷新失败时不要在这里跳转，由调用方决定（store 会交给 sso-session 决策） */
  skipAuthRedirect?: boolean
}

type RetryableRequestConfig = InternalAxiosRequestConfig & RequestOptions & {
  _retry?: boolean
  _retryCount?: number
}

export const DEFAULT_TIMEOUT_MS = 30_000
export const LONG_RUNNING_TIMEOUT_MS = 0
export const UPLOAD_TIMEOUT_MS = 5 * 60_000

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

// 创建 axios 实例
const request: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: DEFAULT_TIMEOUT_MS,
  // 认证依赖后端 httpOnly Cookie，所有请求都必须携带 Cookie
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json'
  },
  // 数组参数必须序列化成重复键（tool_slugs=a&tool_slugs=b）。
  // axios 默认会序列化成 tool_slugs[]=a&tool_slugs[]=b，而 FastAPI 的
  // `Query(None)` 列表参数只认重复键——方括号形式会被当成未知参数**静默忽略**，
  // 于是「按工具过滤」退化成「不过滤」，返回全量任务且不报错。
  // indexes: null 即「不写下标、重复键」，与 FastAPI/Starlette 的解析一致。
  paramsSerializer: {
    indexes: null
  }
})

export { AUTH_CLEARED_EVENT } from '@/utils/auth-storage'

// 清除认证状态
export const clearTokens = (): void => {
  clearAuthStorage()
}

// 是否正在刷新会话
let isRefreshing = false
// 等待刷新的请求队列：刷新成功只广播「可以重放」信号，不再传递 token
type RefreshSubscriber = {
  resolve: () => void
  reject: (error: unknown) => void
}

let refreshSubscribers: RefreshSubscriber[] = []

const subscribeTokenRefresh = (subscriber: RefreshSubscriber) => {
  refreshSubscribers.push(subscriber)
}

const onTokenRefreshed = () => {
  refreshSubscribers.forEach(subscriber => subscriber.resolve())
  refreshSubscribers = []
}

const rejectRefreshSubscribers = (error: unknown) => {
  refreshSubscribers.forEach(subscriber => subscriber.reject(error))
  refreshSubscribers = []
}

// 请求拦截器：不再从 storage 读取 token，非安全方法附加 CSRF 头
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const csrfHeaders = buildCsrfHeader(config.method)
    if (config.headers) {
      Object.entries(csrfHeaders).forEach(([name, value]) => {
        config.headers[name] = value
      })
    }
    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  }
)

// 后端错误 detail 可能为字符串、校验错误数组或对象；统一转成可读且限长的提示，
// 避免把内部细节原样弹窗或渲染出 [object Object]。
const MAX_ERROR_DISPLAY_LENGTH = 200

export const buildErrorDisplayMessage = (error: AxiosError<ApiError>): string => {
  const status = error.response?.status
  const data = error.response?.data
  const raw: unknown = (data as { detail?: unknown; message?: unknown } | undefined)?.detail
    ?? (data as { message?: unknown } | undefined)?.message

  let text = ''
  if (typeof raw === 'string') {
    text = raw.trim()
  } else if (Array.isArray(raw)) {
    const first = raw.find(item => item && typeof item === 'object' && 'msg' in item) as { msg?: unknown } | undefined
    if (first && typeof first.msg === 'string') {
      text = first.msg.trim()
    }
  }
  if (text.length > MAX_ERROR_DISPLAY_LENGTH) {
    text = `${text.slice(0, MAX_ERROR_DISPLAY_LENGTH)}…`
  }
  if (text) {
    return text
  }
  if (status !== undefined && status >= 500) {
    return '服务器内部错误，请稍后重试'
  }
  return '请求失败'
}

// 响应拦截器
request.interceptors.response.use(
  response => {
    return response.data
  },
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as RetryableRequestConfig
    const canRefreshToken = shouldAttemptTokenRefresh(originalRequest?.url)

    // 401 未授权，尝试通过刷新 Cookie 恢复会话
    if (error.response?.status === 401 && canRefreshToken && !originalRequest._retry) {
      if (isRefreshing) {
        // 等待会话刷新完成，成功后直接重放原请求（Cookie 会自动携带）
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh({
            resolve: () => {
              resolve(request(originalRequest))
            },
            reject
          })
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        await axios.post<ApiResponse<unknown>>(
          `${API_BASE_URL}/auth/refresh`,
          undefined,
          { withCredentials: true, headers: buildCsrfHeader('POST') }
        )

        onTokenRefreshed()
        return request(originalRequest)
      } catch (refreshError) {
        // 刷新失败，清除用户态；具体「跳 IAM 还是回登录页」交给唯一决策点，
        // 这里只把 refresh 的原因旁路记下（reject 给调用方的是原始 401，会丢 detail.reason）
        clearTokens()
        rejectRefreshSubscribers(refreshError)
        rememberRefreshFailure(refreshError)
        if (!originalRequest.skipAuthRedirect) {
          applySessionInvalid(readErrorReason(refreshError))
        }
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    }

    const retryCount = originalRequest?._retryCount ?? 0
    const retryLimit = originalRequest?.retry ?? 0
    const method = originalRequest?.method?.toLowerCase()
    const isCanceledRequest = error.code === AxiosError.ERR_CANCELED || error.name === 'CanceledError'
    const retryableStatus = !error.response || (error.response.status >= 500 && error.response.status < 600)
    if (!isCanceledRequest && retryCount < retryLimit && retryableStatus && (method === 'get' || method === 'head')) {
      originalRequest._retryCount = retryCount + 1
      await new Promise(resolve => window.setTimeout(resolve, originalRequest.retryDelayMs ?? 500))
      return request(originalRequest)
    }

    // 其他错误处理
    // 对于 logout 接口的 401 错误，不显示错误消息（因为退出登录即使失败也会清除本地数据）
    const isLogoutRequest = originalRequest.url?.includes('/auth/logout')
    if (!isCanceledRequest && !originalRequest?.silent && !(error.response?.status === 401 && isLogoutRequest)) {
      message.error(buildErrorDisplayMessage(error))
    }

    return Promise.reject(error)
  }
)

// 封装 GET 请求
export const get = <T, P extends object = Record<string, unknown>>(
  url: string,
  params?: P,
  config?: RequestOptions
): Promise<ApiResponse<T>> => {
  return request.get(url, { params, ...config })
}

// 封装 POST 请求
export const post = <T>(url: string, data?: unknown, config?: RequestOptions): Promise<ApiResponse<T>> => {
  return request.post(url, data, config)
}

// 封装 PUT 请求
export const put = <T>(url: string, data?: unknown, config?: RequestOptions): Promise<ApiResponse<T>> => {
  return request.put(url, data, config)
}

// 封装 PATCH 请求
export const patch = <T>(url: string, data?: unknown, config?: RequestOptions): Promise<ApiResponse<T>> => {
  return request.patch(url, data, config)
}

// 封装 DELETE 请求
export const del = <T>(url: string, config?: RequestOptions): Promise<ApiResponse<T>> => {
  return request.delete(url, config)
}

// 封装文件上传
export const upload = <T>(
  url: string,
  file: File,
  onProgress?: (percent: number) => void,
  config?: RequestOptions
): Promise<ApiResponse<T>> => {
  const formData = new FormData()
  formData.append('file', file)

  return request.post(url, formData, {
    ...config,
    timeout: config?.timeout ?? UPLOAD_TIMEOUT_MS,
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    onUploadProgress: progressEvent => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percent)
      }
    }
  })
}

export default request
