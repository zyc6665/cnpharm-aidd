import { get, post, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  ResourceQuotaStatusResponse,
  SystemConfig,
  SystemHealth,
  SystemInfo,
  SystemStats,
  WorkerResourceStatusResponse
} from '@/types/models'

// 系统健康检查
export const getSystemHealth = (config?: RequestOptions): Promise<ApiResponse<SystemHealth>> => {
  return get<SystemHealth>('/system/health', undefined, config)
}

// 获取系统信息
export const getSystemInfo = (): Promise<ApiResponse<SystemInfo>> => {
  return get<SystemInfo>('/system/info')
}

// 获取系统统计
export const getSystemStats = (): Promise<ApiResponse<SystemStats>> => {
  return get<SystemStats>('/system/stats')
}

// 获取在线 Worker 资源状态
export const getWorkerResourceStatus = (): Promise<ApiResponse<WorkerResourceStatusResponse>> => {
  return get<WorkerResourceStatusResponse>('/system/resource-workers')
}

// 获取用户与项目资源配额状态
export const getResourceQuotaStatus = (): Promise<ApiResponse<ResourceQuotaStatusResponse>> => {
  return get<ResourceQuotaStatusResponse>('/system/resource-quotas')
}

// 获取系统配置
export const getSystemConfig = (): Promise<ApiResponse<SystemConfig>> => {
  return get<SystemConfig>('/system/config')
}

