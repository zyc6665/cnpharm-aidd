import { get } from './request'
import type { ApiResponse } from '@/types/api'
import type { SystemConfig, SystemHealth, SystemInfo, SystemStats } from '@/types/models'

// 系统健康检查
export const getSystemHealth = (): Promise<ApiResponse<SystemHealth>> => {
  return get<SystemHealth>('/system/health')
}

// 获取系统信息
export const getSystemInfo = (): Promise<ApiResponse<SystemInfo>> => {
  return get<SystemInfo>('/system/info')
}

// 获取系统统计
export const getSystemStats = (): Promise<ApiResponse<SystemStats>> => {
  return get<SystemStats>('/system/stats')
}

// 获取系统配置
export const getSystemConfig = (): Promise<ApiResponse<SystemConfig>> => {
  return get<SystemConfig>('/system/config')
}
