/**
 * 任务结果里经常混有模型执行时的工作目录（如 `artifacts/lv_results/protein/pocket0.pdb`）。
 * 这些是存储细节，不应该出现在用户界面；展示层统一只取文件名。
 */
export function toDisplayFileName(value: string | null | undefined): string {
  const normalized = String(value ?? '').trim().replace(/\\/g, '/')
  if (!normalized) return ''
  return normalized.split('/').filter(Boolean).pop() ?? normalized
}
