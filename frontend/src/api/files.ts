import { get, post, del } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  ArtifactFile,
  FileInfo,
  FileUploadResponse,
  PaginatedResponse,
  PaginationParams
} from '@/types/models'

// 上传文件
export const uploadFile = (
  file: File,
  options?: {
    is_public?: boolean
    onProgress?: (percent: number) => void
  }
): Promise<ApiResponse<FileUploadResponse>> => {
  const formData = new FormData()
  formData.append('file', file)
  if (options?.is_public !== undefined) {
    formData.append('is_public', String(options.is_public))
  }

  return post<FileUploadResponse>('/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (progressEvent) => {
      if (options?.onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        options.onProgress(percent)
      }
    }
  })
}

// 获取文件列表
export const getFileList = (params?: PaginationParams): Promise<ApiResponse<PaginatedResponse<FileInfo>>> => {
  return get<PaginatedResponse<FileInfo>>('/files', params as Record<string, unknown>)
}

export const getArtifactFiles = (
  params?: PaginationParams & { search?: string }
): Promise<ApiResponse<PaginatedResponse<ArtifactFile>>> => {
  return get<PaginatedResponse<ArtifactFile>>('/files/artifacts', params as Record<string, unknown>)
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
