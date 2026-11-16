import axios, { type AxiosInstance, type AxiosRequestConfig, AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { message } from 'ant-design-vue'
import type { ApiResponse, ApiError } from '@/types/api'
import { shouldAttemptTokenRefresh } from './auth-request-policy'
import { applySessionInvalid, readErrorReason, rememberRefreshFailure } from './sso-session'
import { clearAuthStorage } from '@/utils/auth-storage'
import { buildCsrfHeader, getCsrfToken } from '@/utils/cookies'
import { createRefreshCoordinator, REFRESH_TIMEOUT_MS } from './refresh-coordinator'

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
  /** 本次请求发出时的 CSRF Cookie 值：用来判断刷新期间是否已被另一个标签页换过 */
  _csrfAtSend?: string | null
}

export const DEFAULT_TIMEOUT_MS = 30_000
export const LONG_RUNNING_TIMEOUT_MS = 0
export const UPLOAD_TIMEOUT_MS = 5 * 60_000

// 后端 409 / token_rotated（并发刷新落败）后的重放节奏：先等一小会儿，
// 再轮询 CSRF Cookie 是否已被成功方换掉。
//
// 三条不等式（动任何一项前先读这几个数）：
//   SSO_TIMEOUT_SECONDS * 1000          (5_000，backend/app/config.py:290)
//     <= REFRESH_HANDOFF_MAX_WAIT_MS    (6_000)
//     <  ROTATE_RACE_WINDOW_SECONDS*1000 (10_000；该常量在 backend/app/services/
//        下的刷新令牌存储模块，精确路径见 refresh-coordinator.ts 的常量注释——
//        本文件不写出该文件名：test/user-auth-session.test.ts 会扫描 request.ts，
//        确认这里不再出现把 refresh 令牌塞进请求体的字段名）
//   REFRESH_TIMEOUT_MS                  (9_000，refresh-coordinator.ts) < 10_000
//   REFRESH_HANDOFF_MAX_WAIT_MS (6_000) < REFRESH_TIMEOUT_MS (9_000)
//
// 下限为什么是 SSO_TIMEOUT：赢家的 POST /auth/refresh 要等 IAM 校验，最长 5s 才
// 写回新 Cookie。旧值 2s 小于这个上限——2s 到点时赢家可能还没写完，落败方只能
// 拿着旧 access 重放，必然 401，于是 clearTokens + applySessionInvalid，用户被
// 踢回登录页。那正是本批要消灭的误判。
// 5s 是**整段**校验的上限，不是单次调用：后端 `validate_iam_session` 用
// `budget_seconds=SSO_TIMEOUT_SECONDS` 给「check + 续期」两次串行调用封顶，
// 否则最坏 2×5s 会超过下面的 6s 等待（落败方照样掉线）。
// 上限为什么是竞态窗口：等过 10s，重放时后端已不再把这张旧票判成「并发落败」，
// 而是判成 refresh 复用（401 + 全端吊销）。6s 之后仍等不到就照常重放一次，由服务端
// 裁决（重放若 401，才按会话真失效处理，见下面捕获分支的注释）。
export const REFRESH_HANDOFF_FIRST_DELAY_MS = 200
const REFRESH_HANDOFF_POLL_MS = 100
export const REFRESH_HANDOFF_MAX_WAIT_MS = 6_000

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

// 刷新协调器：跨标签页用 Web Locks 串行化（见 refresh-lock.ts），
// 抢不到锁的一方在锁释放后发现 CSRF 已变，直接交棒由调用方重放。
// 没有 Web Locks（非安全上下文 / 老浏览器）时不假装互斥：两边都会真的发 POST，
// 后到者拿 409/token_rotated，由下面的 handoff 分支接住。
const authRefreshCoordinator = createRefreshCoordinator(async () => {
  await axios.post<ApiResponse<unknown>>(
    `${API_BASE_URL}/auth/refresh`,
    undefined,
    {
      withCredentials: true,
      headers: buildCsrfHeader('POST'),
      timeout: REFRESH_TIMEOUT_MS
    }
  )
})

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

const sleep = (ms: number) => new Promise<void>(resolve => window.setTimeout(resolve, ms))

/** 并发刷新落败：HTTP 409 且 detail.reason 明确是 token_rotated（任意 409 不算）。 */
function isTokenRotatedConflict(error: unknown): boolean {
  const err = error as AxiosError<ApiError> | undefined
  return err?.response?.status === 409 && readErrorReason(err) === 'token_rotated'
}

/**
 * 等成功方把新 CSRF Cookie 写进来。
 *
 * 三态：没有失败时的 CSRF 值 → 只等一小会儿；Cookie 已经变了 → 直接重放；
 * 还是老值 → 轮询到超时（超时后照常重放一次，由服务端裁决）。
 */
async function waitForRefreshHandoff(csrfAtFailure: string | null): Promise<void> {
  if (!csrfAtFailure) {
    await sleep(REFRESH_HANDOFF_FIRST_DELAY_MS)
    return
  }
  if (getCsrfToken() !== csrfAtFailure) {
    return
  }

  const deadline = Date.now() + REFRESH_HANDOFF_MAX_WAIT_MS
  await sleep(REFRESH_HANDOFF_FIRST_DELAY_MS)
  while (Date.now() < deadline) {
    if (getCsrfToken() !== csrfAtFailure) {
      return
    }
    await sleep(REFRESH_HANDOFF_POLL_MS)
  }
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
    const retryableConfig = config as RetryableRequestConfig
    retryableConfig._csrfAtSend = getCsrfToken()
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
        // 跨标签页互斥：拿不到锁的一方等锁释放后发现 CSRF 已变，直接交棒重放，
        // 不再用同一张旧 refresh 二次轮换（那正是后端 409 / token_rotated 的来源）。
        await authRefreshCoordinator.refresh(originalRequest._csrfAtSend ?? null)

        onTokenRefreshed()
        return request(originalRequest)
      } catch (refreshError) {
        if (isTokenRotatedConflict(refreshError)) {
          // 并发落败：不 clearTokens、不跳 IAM，等成功方写好新 Cookie 后重放一次。
          // 重放本身带 _retry=true 与 silent，失败不会再触发刷新或第二次 toast。
          try {
            await waitForRefreshHandoff(originalRequest._csrfAtSend ?? null)
            const replayed = await request({
              ...originalRequest,
              silent: true,
            } as RetryableRequestConfig)
            onTokenRefreshed()
            return replayed
          } catch (replayError) {
            rejectRefreshSubscribers(refreshError)

            // 只有重放真的拿到 401 才算会话失效。409 的交棒只说明「票被换了」，
            // 换来的新 Cookie 到底能不能用，要由这一次重放来回答；网络抖动、超时、
            // 5xx 都只是这一次没成功，顺手清票据再跳登录会把用户无故踢出去。
            //
            // 前提：handoff 预算(6s) >= SSO_TIMEOUT(5s)，赢家最慢的那条路径也已覆盖，
            // 所以「等到超时才重放」在竞态里不会发生；重放若仍 401，只可能是会话
            // 真的失效（或赢家那条路自己也失败了），此时才走既有的清理 + 决策点。
            const replayStatus = (replayError as AxiosError | undefined)?.response?.status
            if (replayStatus !== 401) {
              return Promise.reject(replayError)
            }

            clearTokens()
            rememberRefreshFailure(refreshError)
            if (!originalRequest.skipAuthRedirect) {
              applySessionInvalid(readErrorReason(refreshError))
            }
            return Promise.reject(error)
          }
        }

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
