import { get, post, del, upload } from './request'
import type { ApiResponse } from '@/types/api'
import type { FileInfo, FileUploadResponse, PaginatedResponse, PaginationParams } from '@/types/models'

// 上传文件
export const uploadFile = (file: File, onProgress?: (percent: number) => void): Promise<ApiResponse<FileUploadResponse>> => {
  return upload<FileUploadResponse>('/files/upload', file, onProgress)
}

// 获取文件列表
export const getFileList = (params?: PaginationParams): Promise<ApiResponse<PaginatedResponse<FileInfo>>> => {
  return get<PaginatedResponse<FileInfo>>('/files', params as Record<string, unknown>)
}

// 获取文件信息
export const getFileInfo = (id: number): Promise<ApiResponse<FileInfo>> => {
  return get<FileInfo>(`/files/${id}`)
}

// 获取文件下载 URL
export const getFileDownloadUrl = (id: number): Promise<ApiResponse<{ url: string }>> => {
  return get<{ url: string }>(`/files/${id}/download-url`)
}

// 删除文件
export const deleteFile = (id: number): Promise<ApiResponse<null>> => {
  return del<null>(`/files/${id}`)
}

// 批量删除文件
export const batchDeleteFiles = (ids: number[]): Promise<ApiResponse<null>> => {
  return post<null>('/files/batch-delete', { ids })
}
