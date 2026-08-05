import type { ToolPackage } from '@/types/tool-packages'

export type ToolPackageReadinessType = 'success' | 'warning' | 'error' | 'info'

export interface ToolPackagePublishReadiness {
  type: ToolPackageReadinessType
  message: string
}

export function getToolPackagePublishReadiness(
  item: ToolPackage | null | undefined
): ToolPackagePublishReadiness {
  const version = item?.current_version

  return {
    type: getToolPackagePublishReadinessType(item),
    message: getToolPackagePublishReadinessMessage(item, version)
  }
}

function getToolPackagePublishReadinessType(
  item: ToolPackage | null | undefined
): ToolPackageReadinessType {
  if (item?.status === 'published') return 'success'
  if (!item?.current_version?.is_signed) return 'warning'
  if (item.current_version.validation_status !== 'valid') return 'error'
  return 'info'
}

function getToolPackagePublishReadinessMessage(
  item: ToolPackage | null | undefined,
  version: ToolPackage['current_version'] | undefined
): string {
  if (!version) return '当前 Package 没有版本，不能发布'
  if (item?.status === 'published') return '已发布，可被平台运行时选择'
  if (version.validation_status !== 'valid') return '当前版本未通过契约校验，不能发布'
  if (!version.is_signed || !version.signature) return '当前版本缺少签名，发布前必须补签名'
  return '当前版本已签名且校验通过，可以发布'
}
