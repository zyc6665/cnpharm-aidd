import { get, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type { AssetListParams, AssetListResponse } from '@/types/assets'

/** 数据资产列表统一静默失败（页面自行渲染错态）+ 一次重试。 */
const OPTIONS: RequestOptions = { silent: true, retry: 1 }

export const listProjectAssets = (
  projectId: string,
  params?: AssetListParams
): Promise<ApiResponse<AssetListResponse>> => {
  return get<AssetListResponse, AssetListParams>(
    `/projects/${projectId}/assets`,
    params,
    OPTIONS
  )
}
