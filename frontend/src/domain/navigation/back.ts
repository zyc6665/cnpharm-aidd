/**
 * 「返回」该回哪：能回就回上一页，回不去才退到兜底路径。
 *
 * 平台里几乎所有详情页都写了固定父级（结构详情 → 靶点详情），但用户真实的来路不是树状的：
 * 从「流程总览」点「去结构详情」进来，返回时却被送到靶点详情，等于把用户从流程里拽了出去。
 * 浏览器的历史记录才是真实的来路，所以默认走历史；只有直接打开链接（历史里没有上一条）时
 * 才退回父级，保证「返回」永远有去处。
 */

export interface BackDecisionInput {
  /** 浏览器历史里的上一条路径；Vue Router 会把它放在 `history.state.back`。 */
  historyBack: string | null | undefined
  /** 当前页面的完整路径，用来避免「上一条就是自己」导致原地打转。 */
  currentPath: string
  /** 历史不可用时的兜底路径。 */
  fallback: string
}

export interface BackDecision {
  mode: 'back' | 'push'
  to: string
}

export function resolveBackTarget(input: BackDecisionInput): BackDecision {
  const previous = typeof input.historyBack === 'string' ? input.historyBack.trim() : ''
  if (previous && previous !== input.currentPath) {
    return { mode: 'back', to: previous }
  }
  return { mode: 'push', to: input.fallback }
}

/** 从浏览器的 history.state 里读「上一条路径」，读不到就返回 null。 */
export function readHistoryBack(state: unknown): string | null {
  if (!state || typeof state !== 'object') return null
  const back = (state as { back?: unknown }).back
  return typeof back === 'string' && back ? back : null
}
