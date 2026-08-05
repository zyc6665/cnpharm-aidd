import { get, post } from './request'
import type { PaginatedResponse } from '@/types/models'
import type { ToolPackage, ToolPackageCreateInput } from '@/types/tool-packages'

export const listToolPackages = (params?: { page?: number; page_size?: number }) =>
  get<PaginatedResponse<ToolPackage>>('/tool-packages', params, { silent: true, retry: 1 })

export const createToolPackage = (data: ToolPackageCreateInput) =>
  post<ToolPackage>('/tool-packages', data, { silent: true })

export const getToolPackage = (packageId: string) =>
  get<ToolPackage>(`/tool-packages/${packageId}`, undefined, { silent: true, retry: 1 })

export const publishToolPackage = (packageId: string) =>
  post<ToolPackage>(`/tool-packages/${packageId}/publish`, undefined, { silent: true })
