/**
 * antd `a-pagination` 的页码/页大小变更归一化。
 *
 * 背景：`a-pagination` 在「改页大小」时会**连发两个事件**——
 * 先 `showSizeChange(current, size)`，再 `change(current, size)`，
 * 且第二个事件的 `current` 是**旧的页码**（antd 保留当前页而不是回到第 1 页）。
 *
 * 因此页面如果同时绑 `@change` 与 `@show-size-change`，会出现两个问题：
 * 1. 一次操作打两次请求；
 * 2. 后到的 `@change` 把「改页大小应回到第 1 页」的赋值覆盖回旧页码，
 *    用户改完页大小仍停在原来的页码，而该页在新页大小下可能已越界。
 *
 * 约定：页面只绑 `@change`，把 `(page, size)` 一起交给本函数，
 * 由它按「页大小是否变化」决定页码——变化则回第 1 页，否则用新页码。
 */

export interface PaginationChangeInput {
  /** 事件里的页码（改页大小时是 antd 保留的旧页码） */
  nextPage: number
  /** 事件里的页大小；`a-pagination` 的 `change` 在未改大小时可能不传 */
  nextSize?: number | null
  /** 当前页大小，用于判断本次事件是否由「改页大小」触发 */
  currentSize: number
}

export interface PaginationChangeResult {
  page: number
  /** 页大小发生变化时返回新值，否则为 `null`（调用方保持原值） */
  size: number | null
}

/** 页码至少是 1；非整数（antd 理论上不会传）按 1 处理，避免请求带 `page=NaN` */
function normalizePage(value: number): number {
  if (!Number.isFinite(value)) {
    return 1
  }
  const rounded = Math.trunc(value)
  return rounded < 1 ? 1 : rounded
}

/** 页大小必须是正整数；非法值返回 `null` 表示「不采用」 */
function normalizeSize(value: number | null | undefined): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return null
  }
  const rounded = Math.trunc(value)
  return rounded < 1 ? null : rounded
}

/**
 * 计算一次 `change` 事件之后应该使用的页码与页大小。
 *
 * - 页大小变了 → 回到第 1 页（`nextPage` 在这条路径上是旧页码，必须忽略）
 * - 页大小没变 → 使用事件里的 `nextPage`
 * - 页大小非法（undefined / NaN / < 1）→ 视为没变
 */
export function resolvePaginationChange(input: PaginationChangeInput): PaginationChangeResult {
  const size = normalizeSize(input.nextSize)
  const currentSize = normalizeSize(input.currentSize)

  if (size !== null && size !== currentSize) {
    return { page: 1, size }
  }

  return { page: normalizePage(input.nextPage), size: null }
}
