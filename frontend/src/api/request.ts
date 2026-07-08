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
  AUTH_CLEARED_EVENT,
  clearAuthStorage,
  getGuestSession,
  getRefreshToken,
  getToken,
  setRefreshToken,
  setToken
} from '@/utils/auth-storage'

// 创建 axios 实例
const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

export {
  AUTH_CLEARED_EVENT,
  getGuestSession,
  getRefreshToken,
  getToken,
  setRefreshToken,
  setToken,
  setGuestSession
} from '@/utils/auth-storage'

// 清除认证状态
export const clearTokens = (): void => {
  clearAuthStorage()
}

// 是否正在刷新 Token
let isRefreshing = false
// 等待刷新的请求队列
let refreshSubscribers: ((token: string) => void)[] = []

// 订阅 Token 刷新
const subscribeTokenRefresh = (cb: (token: string) => void) => {
  refreshSubscribers.push(cb)
}

// 通知所有订阅者
const onTokenRefreshed = (token: string) => {
  refreshSubscribers.forEach(cb => cb(token))
  refreshSubscribers = []
}

// 请求拦截器
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getToken()
    if (token && config.headers && shouldAttachAuthHeader(config.url)) {
      config.headers.Authorization = `Bearer ${token}`
    } else {
      const guestSession = getGuestSession()
      if (guestSession && config.headers && shouldAttachAuthHeader(config.url)) {
        config.headers['X-Guest-Session'] = guestSession
      }
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
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    const canRefreshToken = shouldAttemptTokenRefresh(originalRequest?.url)

    // 401 未授权，尝试刷新 Token
    if (error.response?.status === 401 && canRefreshToken && !originalRequest._retry) {
      if (isRefreshing) {
        // 等待 Token 刷新完成
        return new Promise(resolve => {
          subscribeTokenRefresh((token: string) => {
            if (originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${token}`
            }
            resolve(request(originalRequest))
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
          redirectToLogin(window.location.pathname)
          return Promise.reject(error)
        } finally {
          isRefreshing = false
        }
      } else {
        // 没有 Refresh Token，跳转登录
        clearTokens()
        redirectToLogin(window.location.pathname)
      }
    }

    // 其他错误处理
    // 对于 logout 接口的 401 错误，不显示错误消息（因为退出登录即使失败也会清除本地数据）
    const isLogoutRequest = originalRequest.url?.includes('/auth/logout')
    if (!(error.response?.status === 401 && isLogoutRequest)) {
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
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  return request.get(url, { params, ...config })
}

// 封装 POST 请求
export const post = <T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<ApiResponse<T>> => {
  return request.post(url, data, config)
}

// 封装 PUT 请求
export const put = <T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<ApiResponse<T>> => {
  return request.put(url, data, config)
}

// 封装 PATCH 请求
export const patch = <T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<ApiResponse<T>> => {
  return request.patch(url, data, config)
}

// 封装 DELETE 请求
export const del = <T>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> => {
  return request.delete(url, config)
}

// 封装文件上传
export const upload = <T>(url: string, file: File, onProgress?: (percent: number) => void): Promise<ApiResponse<T>> => {
  const formData = new FormData()
  formData.append('file', file)

  return request.post(url, formData, {
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
