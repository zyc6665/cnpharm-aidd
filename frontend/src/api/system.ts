import { get } from './request'
import type { ApiResponse } from '@/types/api'
import type { SystemHealth, SystemStats, GPUSummary, GPUInfo } from '@/types/models'

// 系统健康检查
export const getSystemHealth = (): Promise<ApiResponse<SystemHealth>> => {
  return get<SystemHealth>('/system/health')
}

// 获取系统信息
export const getSystemInfo = (): Promise<ApiResponse<Record<string, unknown>>> => {
  return get<Record<string, unknown>>('/system/info')
}

// 获取系统统计
export const getSystemStats = (): Promise<ApiResponse<SystemStats>> => {
  return get<SystemStats>('/system/stats')
}

// 获取系统配置
export const getSystemConfig = (): Promise<ApiResponse<Record<string, unknown>>> => {
  return get<Record<string, unknown>>('/system/config')
}

// ==================== GPU 相关接口（后端GPU路由未注册，暂时不可用） ====================

// 获取 GPU 信息（后端未注册GPU路由）
// export const getGPUInfo = (): Promise<ApiResponse<GPUInfo[]>> => {
//   return get<GPUInfo[]>('/gpu/info')
// }

// 获取 GPU 摘要（后端未注册GPU路由）
// export const getGPUSummary = (): Promise<ApiResponse<GPUSummary>> => {
//   return get<GPUSummary>('/gpu/summary')
// }

// 获取 GPU 统计（后端未注册GPU路由）
// export const getGPUStats = (): Promise<ApiResponse<GPUInfo[]>> => {
//   return get<GPUInfo[]>('/gpu/stats')
// }

// GPU 健康检查（后端未注册GPU路由）
// export const getGPUHealth = (): Promise<ApiResponse<{ healthy: boolean; message: string }>> => {
//   return get<{ healthy: boolean; message: string }>('/gpu/health')
// }
