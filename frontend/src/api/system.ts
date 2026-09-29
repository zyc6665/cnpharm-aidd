import { del, get, post, put, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  ModelService,
  ModelServiceCreateParams,
  ModelServiceListResponse,
  ModelServiceModelsResponse,
  ModelServiceTestResult,
  ModelServiceUpdateParams,
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

// 获取模型服务设置
export const getModelServices = (): Promise<ApiResponse<ModelServiceListResponse>> => {
  return get<ModelServiceListResponse>('/system/model-services')
}

// 创建模型服务设置
export const createModelService = (
  data: ModelServiceCreateParams
): Promise<ApiResponse<ModelService>> => {
  return post<ModelService>('/system/model-services', data)
}

// 更新模型服务设置
export const updateModelService = (
  serviceId: string,
  data: ModelServiceUpdateParams
): Promise<ApiResponse<ModelService>> => {
  return put<ModelService>(`/system/model-services/${serviceId}`, data)
}

// 删除模型服务设置
export const deleteModelService = (serviceId: string): Promise<ApiResponse<{ id: string }>> => {
  return del<{ id: string }>(`/system/model-services/${serviceId}`)
}

// 测试模型服务连接
export const testModelService = (
  serviceId: string
): Promise<ApiResponse<ModelServiceTestResult>> => {
  return post<ModelServiceTestResult>(`/system/model-services/${serviceId}/test`)
}

export const discoverModelServiceModels = (
  serviceId: string
): Promise<ApiResponse<ModelServiceModelsResponse>> => {
  return get<ModelServiceModelsResponse>(`/system/model-services/${serviceId}/models`)
}

// 设置默认模型服务
export const setDefaultModelService = (serviceId: string): Promise<ApiResponse<ModelService>> => {
  return post<ModelService>(`/system/model-services/${serviceId}/set-default`)
}
