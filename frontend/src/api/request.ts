import axios, { type AxiosInstance, type AxiosRequestConfig, AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { message } from 'ant-design-vue'
import type { ApiResponse, ApiError } from '@/types/api'
import {
  buildRefreshTokenRequestConfig,
  shouldAttachAuthHeader,
  shouldAttemptTokenRefresh
} from './auth-request-policy'
import { redirectToLogin } from './auth-redirect'
import {
  clearAuthStorage,
  getRefreshToken,
  getToken,
  setRefreshToken,
  setToken
} from '@/utils/auth-storage'

export interface RequestOptions extends AxiosRequestConfig {
  silent?: boolean
  retry?: number
  retryDelayMs?: number
}

type RetryableRequestConfig = InternalAxiosRequestConfig & RequestOptions & {
  _retry?: boolean
  _retryCount?: number
}

export const DEFAULT_TIMEOUT_MS = 30_000
export const LONG_RUNNING_TIMEOUT_MS = 0
export const UPLOAD_TIMEOUT_MS = 5 * 60_000

// 创建 axios 实例
const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: DEFAULT_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json'
  }
})

export {
  AUTH_CLEARED_EVENT,
  getRefreshToken,
  getToken,
  setRefreshToken,
  setToken
} from '@/utils/auth-storage'

// 清除认证状态
export const clearTokens = (): void => {
  clearAuthStorage()
}

// 是否正在刷新 Token
let isRefreshing = false
// 等待刷新的请求队列
type RefreshSubscriber = {
  resolve: (token: string) => void
  reject: (error: unknown) => void
}

let refreshSubscribers: RefreshSubscriber[] = []

// 订阅 Token 刷新
const subscribeTokenRefresh = (subscriber: RefreshSubscriber) => {
  refreshSubscribers.push(subscriber)
}

// 通知所有订阅者
const onTokenRefreshed = (token: string) => {
  refreshSubscribers.forEach(subscriber => subscriber.resolve(token))
  refreshSubscribers = []
}

const rejectRefreshSubscribers = (error: unknown) => {
  refreshSubscribers.forEach(subscriber => subscriber.reject(error))
  refreshSubscribers = []
}

// 请求拦截器
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getToken()
    if (token && config.headers && shouldAttachAuthHeader(config.url)) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  response => {
    return response.data
  },
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as RetryableRequestConfig
    const canRefreshToken = shouldAttemptTokenRefresh(originalRequest?.url)

    // 401 未授权，尝试刷新 Token
    if (error.response?.status === 401 && canRefreshToken && !originalRequest._retry) {
      if (isRefreshing) {
        // 等待 Token 刷新完成
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh({
            resolve: (token: string) => {
              if (originalRequest.headers) {
                originalRequest.headers.Authorization = `Bearer ${token}`
              }
              resolve(request(originalRequest))
            },
            reject
          })
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      const refreshToken = getRefreshToken()
      if (refreshToken) {
        try {
          const response = await axios.post<ApiResponse<{ access_token: string; refresh_token: string }>>(
            `${import.meta.env.VITE_API_BASE_URL}/auth/refresh`,
            undefined,
            buildRefreshTokenRequestConfig(refreshToken)
          )

          const { access_token, refresh_token: newRefreshToken } = response.data.data
          setToken(access_token)
          setRefreshToken(newRefreshToken)
          onTokenRefreshed(access_token)

          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${access_token}`
          }
          return request(originalRequest)
        } catch {
          // 刷新失败，清除 Token 并跳转登录
          clearTokens()
          rejectRefreshSubscribers(error)
          redirectToLogin(window.location.pathname)
          return Promise.reject(error)
        } finally {
          isRefreshing = false
        }
      } else {
        // 没有 Refresh Token，跳转登录
        clearTokens()
        rejectRefreshSubscribers(error)
        isRefreshing = false
        redirectToLogin(window.location.pathname)
        return Promise.reject(error)
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
      const errorMessage = error.response?.data?.message || error.message || '请求失败'
      message.error(errorMessage)
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
