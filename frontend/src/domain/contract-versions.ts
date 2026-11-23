/**
 * Platform contract literals.
 *
 * 2026-11 命名收敛：平台产出 `aidd.platform/*`；旧产品线命名 `aidd.platform/*`
 * 继续只读接受，避免存量 ToolPackage / result 在管理端与运行表单里失效。
 */
export const TOOL_PACKAGE_API_VERSION = 'aidd.platform/tool-package'
export const LEGACY_TOOL_PACKAGE_API_VERSION = 'aidd.platform/tool-package'
export const TOOL_PACKAGE_API_VERSIONS: readonly string[] = [
  TOOL_PACKAGE_API_VERSION,
  LEGACY_TOOL_PACKAGE_API_VERSION
]

export const RESULT_VERSION = 'aidd.platform/result'
export const RESULT_VERSION_V2 = 'aidd.platform/result.v2'
export const LEGACY_RESULT_VERSION = 'aidd.platform/result'
export const LEGACY_RESULT_VERSION_V2 = 'aidd.platform/result.v2'
export const RESULT_VERSIONS: readonly string[] = [
  RESULT_VERSION,
  RESULT_VERSION_V2,
  LEGACY_RESULT_VERSION,
  LEGACY_RESULT_VERSION_V2
]

export function isToolPackageApiVersion(value: unknown): boolean {
  return typeof value === 'string' && TOOL_PACKAGE_API_VERSIONS.includes(value)
}

export function isResultVersion(value: unknown): boolean {
  return typeof value === 'string' && RESULT_VERSIONS.includes(value)
}
